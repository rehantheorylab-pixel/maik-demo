import hashlib
import json
from typing import Optional
from config import cfg, corp, experts, council, TokenBudget
from blackboard import blackboard, internal_notes

_pattern_cache: dict[str, dict] = {}
_ceo_routing_log: list[dict] = []
_cache_hits = 0
_cache_misses = 0

def _hash_sig(problem: str, domain: str = "") -> str:
    return hashlib.sha256(f"{domain}:{problem.strip().lower()[:200]}".encode()).hexdigest()

def _classify_problem(problem: str, budget: TokenBudget) -> str:
    domains = ["code", "math", "planning", "creative", "research", "security", "general"]
    keywords = {
        "code": ["write", "function", "class", "bug", "code", "implement", "program", "script", "api", "endpoint"],
        "math": ["solve", "calculate", "equation", "formula", "proof", "integral", "derivative", "sum"],
        "planning": ["plan", "strategy", "step", "approach", "design", "architecture", "roadmap"],
        "creative": ["write a story", "poem", "creative", "idea", "design", "generate"],
        "research": ["find", "research", "explore", "investigate", "what is", "how does"],
        "security": ["security", "vulnerability", "attack", "threat", "audit", "CVE"],
    }
    pl = problem.lower()
    scores = {}
    for domain, kwlist in keywords.items():
        scores[domain] = sum(pl.count(kw) * (3 if len(kw) > 5 else 1) for kw in kwlist)
    if not scores or max(scores.values()) == 0:
        return "general"
    return max(scores, key=scores.get)

def route(problem: str, domain: str = "", budget: Optional[TokenBudget] = None) -> dict:
    global _cache_hits, _cache_misses
    budget = budget or TokenBudget()
    sig = _hash_sig(problem, domain)

    if sig in _pattern_cache:
        _cache_hits += 1
        cached = _pattern_cache[sig]
        budget.spend(0)
        return {**cached, "cached": True, "tokens": 0, "budget": str(budget)}

    _cache_misses += 1
    prob_type = _classify_problem(problem, budget)

    ceo = council.ceo_for_domain(domain or prob_type)
    ceo_budget = council.budget_for(ceo.id)
    ceo_budget.spend(0)

    expert_name = experts.find_expert(domain or prob_type, problem)
    expert_info = experts.experts.get(expert_name, experts.experts["synthesizer"])
    mode = budget.mode()
    model_info = cfg.pick_model("route", mode)
    confidence = 0.8 if prob_type != "general" else 0.6
    estimated = int(len(problem) * 0.25) + 100
    budget.spend(estimated)

    if expert_info["model"] == "large" and not budget.enough_for_full_run():
        expert_name = "planner"
        expert_info = experts.experts["planner"]
        confidence = 0.5

    decision = {
        "expert": expert_name,
        "model": model_info["name"],
        "model_full": model_info["model"],
        "problem_type": prob_type,
        "confidence": confidence,
        "domain": domain or prob_type,
        "ceo": ceo.id,
        "ceo_name": ceo.name,
        "ceo_managers": ceo.min_managers,
        "ceo_budget": str(ceo_budget),
        "explanation": f"CEO '{ceo.name}' assigned, classified as {prob_type}, routed to {expert_name}",
        "cached": False,
        "tokens_estimated": estimated,
        "budget": str(budget),
        "budget_mode": mode,
        "cache_stats": {"hits": _cache_hits, "misses": _cache_misses, "hit_rate": _cache_hits / max(_cache_hits + _cache_misses, 1)},
    }

    _pattern_cache[sig] = decision
    _ceo_routing_log.append({"problem": problem[:60], "ceo": ceo.id, "domain": domain or prob_type, "time": __import__('time').time()})
    blackboard.write(f"route:{sig}", json.dumps(decision), "router", confidence)
    internal_notes.write("router", f"CEO '{ceo.id}' -> {expert_name} for '{problem[:60]}...'", "public", confidence)
    return decision

def clear_cache():
    _pattern_cache.clear()
    global _cache_hits, _cache_misses
    _cache_hits = _cache_misses = 0

def cache_stats() -> dict:
    return {"size": len(_pattern_cache), "hits": _cache_hits, "misses": _cache_misses, "hit_rate": _cache_hits / max(_cache_hits + _cache_misses, 1)}

def ceo_routing_log() -> list[dict]:
    return _ceo_routing_log[-50:]
