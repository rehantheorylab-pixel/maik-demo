import time
import json
import uuid
from typing import Optional
from config import cfg, corp, council, TokenBudget
from blackboard import blackboard, internal_notes
from router_engine import route

_execution_log: list[dict] = []
_ceo_execution_map: dict[str, int] = {}

class AgentNode:
    def __init__(self, agent_id: str, role: str, depth: int, parent_id: Optional[str] = None, ceo_id: str = ""):
        self.id = agent_id
        self.role = role
        self.depth = depth
        self.parent_id = parent_id
        self.ceo_id = ceo_id
        self.children: list[str] = []
        self.state = "pending"
        self.confidence = 0.0
        self.tokens_used = 0
        self.output = ""
        self.started_at = time.time()
        self.completed_at: Optional[float] = None

def _llm_call(model_cfg: dict, prompt: str, budget: TokenBudget, agent_id: str) -> tuple[str, int]:
    estimated = int(len(prompt) * 0.25) + 500
    if not budget.can_afford(estimated):
        model_cfg = cfg.pick_model("route", "survival")
        estimated = int(len(prompt) * 0.15) + 100
        if not budget.can_afford(estimated):
            return "BUDGET_EXHAUSTED_CANNOT_PROCESS", 0
    try:
        import litellm
        resp = litellm.completion(
            model=model_cfg["model"],
            messages=[
                {"role": "system", "content": f"You are {agent_id} in MAIK. Budget: {budget}. Use NOTE(content) for internal notes. Use CHAT(message) for public chat."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=min(2000, budget.remaining // 2),
            temperature=0.7,
            timeout=30
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if hasattr(resp, 'usage') and resp.usage else estimated
    except Exception as e:
        text = f"LLM_ERROR: {e}"
        tokens = estimated
    budget.spend(tokens)
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        s = line.strip()
        if s.startswith("NOTE(") and ")" in s:
            content = s[5:s.index(")")]
            internal_notes.write(agent_id, content, "public", 1.0)
        elif s.startswith("CHAT(") and ")" in s:
            content = s[5:s.index(")")]
            blackboard.write(f"chat:{agent_id}:{int(time.time()*1000)}", content, agent_id)
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines), tokens

def _decompose(problem: str, depth: int, budget: TokenBudget, ceo_id: str = "") -> list[str]:
    if depth >= cfg.recursion_threshold:
        return [problem]
    model_cfg = cfg.pick_model("decompose", budget.mode())
    ceo_hint = f" (under CEO: {ceo_id})" if ceo_id else ""
    prompt = f"Break this problem into 2-4 parallel sub-problems{ceo_hint}. Return one per line, numbered.\n\nProblem: {problem}"
    text, tokens = _llm_call(model_cfg, prompt, budget, f"decomposer-d{depth}")
    subs = [l.strip().lstrip("0123456789.-) ").strip() for l in text.split("\n") if l.strip() and not l.startswith("NOTE(")]
    return subs[:4] if len(subs) >= 2 else [problem]

def _predictive_value(problem: str, role: str, budget: TokenBudget) -> float:
    est = int(len(problem) * 0.25) + 2000
    if not budget.can_afford(est):
        return 0.1
    return 0.7

def _run_agent(problem: str, role: str, depth: int, budget: TokenBudget,
               parent_id: str = "", context: Optional[dict] = None, ceo_id: str = "") -> AgentNode:
    context = context or {}
    agent_id = f"{role}-{depth}-{uuid.uuid4().hex[:6]}"
    node = AgentNode(agent_id, role, depth, parent_id or None, ceo_id)
    if _predictive_value(problem, role, budget) < cfg.predictive_prune_threshold:
        node.state = "skipped"
        node.output = "Skipped by predictive pruner (low expected value)"
        node.confidence = 0.0
        node.completed_at = time.time()
        _execution_log.append({"agent": agent_id, "role": role, "depth": depth, "state": "skipped", "tokens": 0, "duration": 0, "parent": parent_id, "ceo": ceo_id})
        return node
    node.state = "running"
    model_cfg = cfg.pick_model(role, budget.mode())
    chat_context = blackboard.get_chat_log(10)
    notes_context = internal_notes.get_all_public()
    parts = [
        f"Problem: {problem}",
        f"Role: {role} at depth {depth} ({corp.role_at_depth(depth)})",
        f"CEO: {ceo_id or 'unassigned'}",
        f"Budget: {budget} (mode: {budget.mode()})",
        f"Permission tier: {corp.permission_tier(depth, 'execute')}",
    ]
    if chat_context:
        parts.append(f"Chat:\n" + "\n".join(str(c)[:100] for c in chat_context))
    if notes_context:
        parts.append(f"Notes:\n{notes_context[:500]}")
    if context.get("sub_problem"):
        parts.append(f"Sub-problem: {context['sub_problem']}")
    if context.get("sibling_outputs"):
        parts.append(f"Siblings:\n{context['sibling_outputs'][:300]}")
    parts.append("NOTE(content) for notes. CHAT(msg) for public chat.")
    output, tokens = _llm_call(model_cfg, "\n\n".join(parts), budget, agent_id)
    node.output = output
    node.tokens_used = tokens
    node.state = "completed"
    node.confidence = 0.75 if "BUDGET_EXHAUSTED" not in output and "LLM_ERROR" not in output else 0.3
    node.completed_at = time.time()
    blackboard.write(f"agent:{agent_id}:output", output[:500], agent_id, node.confidence)
    internal_notes.write(agent_id, f"Completed {role}: {output[:80]}...", "public", node.confidence)
    _execution_log.append({
        "agent": agent_id, "role": role, "depth": depth, "state": "completed",
        "tokens": tokens, "duration": node.completed_at - node.started_at,
        "parent": parent_id, "confidence": node.confidence, "ceo": ceo_id,
    })
    _ceo_execution_map[ceo_id] = _ceo_execution_map.get(ceo_id, 0) + 1
    return node

def _synthesize(results: list[AgentNode], problem: str, budget: TokenBudget) -> tuple[str, float]:
    if not results:
        return "No output", 0.0
    if len(results) == 1:
        return results[0].output, results[0].confidence
    model_cfg = cfg.pick_model("synthesize", budget.mode())
    inputs = "\n\n".join(f"[{n.role}] conf={n.confidence:.2f}:\n{n.output[:300]}" for n in results)
    text, tokens = _llm_call(model_cfg, f"Merge these into one answer. Prefer simplest.\n\nProblem: {problem}\n\n{inputs}", budget, f"synth-{uuid.uuid4().hex[:6]}")
    avg_c = sum(n.confidence for n in results) / len(results)
    return text, avg_c

def _build_response(solution: str, confidence: float, depth: int, agents: list, budget: TokenBudget,
                    sub_problems: Optional[list] = None, truncated: bool = False, ceo_id: str = "") -> dict:
    return {
        "solution": solution, "confidence": confidence, "depth": depth,
        "sub_problems": sub_problems or [],
        "agents_used": [{"id": a.id, "role": a.role, "tokens": a.tokens_used, "state": a.state, "confidence": a.confidence, "ceo": a.ceo_id} for a in agents],
        "budget": str(budget), "budget_mode": budget.mode(),
        "truncated": truncated, "ceo": ceo_id,
        "ceo_execution_counts": dict(_ceo_execution_map),
        "notes": internal_notes.to_dict(requester_depth=depth),
        "chat_log": blackboard.get_chat_log(10),
        "agents_log": _execution_log[-30:],
    }

def execute(problem: str, domain: str = "", budget: Optional[TokenBudget] = None, depth: int = 0, parent_id: str = "") -> dict:
    budget = budget or TokenBudget()
    route_result = route(problem, domain, budget)
    ceo_id = route_result.get("ceo", "")
    ceo_profile = council.ceo_by_id(ceo_id)
    ceo_max_depth = ceo_profile.max_depth if ceo_profile else cfg.max_depth
    _execution_log.append({"phase": "start", "problem": problem[:80], "depth": depth, "ceo": ceo_id, "budget": str(budget), "mode": budget.mode()})
    if depth >= ceo_max_depth:
        agent = _run_agent(problem, "worker", depth, budget, parent_id, ceo_id=ceo_id)
        return _build_response(agent.output, agent.confidence, depth, [agent], budget, truncated=True, ceo_id=ceo_id)
    sub_problems = _decompose(problem, depth, budget, ceo_id)
    if len(sub_problems) <= 1:
        role = "executor" if depth % 2 == 0 else "explorer"
        agent = _run_agent(problem, role, depth, budget, parent_id, ceo_id=ceo_id)
        return _build_response(agent.output, agent.confidence, depth, [agent], budget, sub_problems=[problem], ceo_id=ceo_id)
    results: list[AgentNode] = []
    for i, sp in enumerate(sub_problems):
        if not budget.can_afford(2000) and i > 0:
            break
        sub_depth = depth + 1
        if sub_depth <= cfg.recursion_threshold:
            sub = execute(sp, domain, budget, sub_depth, f"parent-d{depth}")
            sn = AgentNode(f"subtree-{i}", "subtree", sub_depth, f"parent-d{depth}", ceo_id)
            sn.output = sub.get("solution", "")
            sn.confidence = sub.get("confidence", 0.5)
            sn.tokens_used = sum(a.get("tokens", 0) for a in sub.get("agents_used", []))
            sn.state = "completed"
            results.append(sn)
        else:
            sib = "\n".join(r.output[:200] for r in results)
            role = ["executor", "reviewer", "explorer"][i % 3]
            results.append(_run_agent(sp, role, sub_depth, budget, f"parent-d{depth}", {"sub_problem": sp, "sibling_outputs": sib}, ceo_id=ceo_id))
    solution, confidence = _synthesize(results, problem, budget)
    internal_notes.write("synthesizer", f"CEO '{ceo_id}' depth {depth}: merged {len(results)} agents (conf={confidence:.2f})", "public", confidence)
    blackboard.write(f"solution:d{depth}", solution[:500], "synthesizer", confidence)
    return _build_response(solution, confidence, depth, results, budget, sub_problems, ceo_id=ceo_id)

def get_execution_log() -> list[dict]:
    return _execution_log[-100:]

def ceo_execution_breakdown() -> dict:
    return dict(_ceo_execution_map)
