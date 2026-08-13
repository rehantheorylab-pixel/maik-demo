"""Execution engine — upgrade U1+U3: tiered cascade with cost ledger.

Flow per problem:
  1. route (router.py) -> (CEO, expert, tier)
  2. execute on the assigned tier (flash first = free)
  3. grade confidence of the result; if below config threshold and budget
     allows, ESCALATE one tier (max config.friction.max_escalations)
  4. record outcome -> pattern cache performance curve + budget ledger

No paid call is ever made unless free tiers fail AND the problem genuinely
demands escalation. The cost ledger proves how cheap the cascade is.
"""

import time
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .blackboard import Blackboard
from .config import Config, ModelTier
from .executor_org import OrgBridge
from .providers import ProviderLadder
from .router import Router, RoutingDecision
from .safety import SafetyGate

TIER_ORDER = [ModelTier.FLASH, ModelTier.SMALL, ModelTier.MEDIUM, ModelTier.LARGE]


def _grade_answer(problem: str, answer: str) -> float:
    """Cheap structural quality gate before any expensive verification.

    Score 0.0-1.0 based on: non-empty, no error markers, length sanity,
    and answer-problem overlap heuristics. A verifier agent (Phase C)
    replaces this with real semantic grading.
    """
    if not answer or not answer.strip():
        return 0.0
    a = answer.strip()
    if a.upper().startswith(("ERROR", "LLM_ERROR", "EXCEPTION", "TIMEOUT")):
        return 0.1
    words = len(a.split())
    # numeric answers to calculation problems pass cheaply — shortness is
    # precision, not weakness
    if words <= 2 and re.fullmatch(r"[\d\.,%eE\-\+ ]+", a):
        return 0.85
    if words < 2:
        return 0.4
    problem_words = set(problem.lower().split())
    # generic answer ("yes"/"no"/"42") is weak for open questions
    if words <= 3 and len(problem_words) > 8:
        return 0.45
    return 0.75


@dataclass
class ExecutionResult:
    run_id: str
    problem: str
    decision: RoutingDecision
    answer: str
    confidence: float
    tier_used: ModelTier
    escalations: int
    provider: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_s: float
    agents_used: int
    notes: List[Dict[str, Any]]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "problem": self.problem,
            "decision": self.decision.to_dict(),
            "solution": self.answer,
            "confidence": round(self.confidence, 3),
            "tier_used": self.tier_used.value,
            "escalations": self.escalations,
            "provider": self.provider,
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "duration_s": round(self.duration_s, 3),
            "agents_used": self.agents_used,
            "notes": self.notes,
        }


class Executor:
    TIER_UP = {ModelTier.FLASH: ModelTier.SMALL,
               ModelTier.SMALL: ModelTier.MEDIUM,
               ModelTier.MEDIUM: ModelTier.LARGE,
               ModelTier.LARGE: None}

    def __init__(self, config: Config, ladder: Optional[ProviderLadder] = None,
                 pattern_lib: Optional["PatternLibrary"] = None,
                 org_bridge: Optional[OrgBridge] = None):
        self.config = config
        self.ladder = ladder or ProviderLadder()
        self.blackboard = Blackboard()
        self.safety = SafetyGate(config)
        self.pattern_lib = pattern_lib
        self.org = org_bridge  # Phase H org-aware layer (optional)
        self._results: List[ExecutionResult] = []

    def execute(self, problem: str, max_tokens: int = 2048) -> ExecutionResult:
        run_id = uuid.uuid4().hex[:12]
        t0 = time.time()
        decision = self._router().route(problem)  # lazy router
        ceo = self.config.ceo_for_domain(decision.ceo_domain) or self.config.ceos[0]
        notes: List[Dict[str, Any]] = []

        # safety: budget tripwire check before spend
        self.safety.check(ceo)

        # Phase H: select an org worker node if the org layer is active
        worker = (self.org.select_worker(decision.problem_type,
                                         decision.ceo_domain)
                  if self.org and self.org.active else None)

        tier = decision.tier
        escalations = 0
        last = None
        run_model = None
        # Pattern Library v0: hot-swap specialist reasoning patterns in place
        matched = self.pattern_lib.match(problem) if self.pattern_lib else []
        if matched:
            pat = matched[0]
            decision.tier = pat.tier_hint  # pattern knows its preferred tier
            tier = pat.tier_hint
            pattern_prefix = pat.prompt_prefix
            notes.append({"agent": "pattern_lib", "event": "matched",
                          "pattern": pat.name, "domain": pat.domain})
        else:
            pattern_prefix = ""
        while tier is not None:
            if self.config.budgets.remaining(ceo) <= 0:
                notes.append({"agent": "safety", "event": "budget_denied", "tier": tier.value})
                break
            # Phase H: org system prompt (self-aware) when a worker is selected,
            # else the classic single-agent system prompt
            if worker is not None:
                sys_content = self.org.build_system_prompt(worker,
                                                           decision.problem_type)
                if pattern_prefix:
                    sys_content += "\n\n" + pattern_prefix
                model = self.org.resolve_model(worker.uid, tier)
                run_model = model
            else:
                sys_content = (f"You are the {decision.expert} specialist under "
                               f"CEO {ceo.name} ({decision.problem_type} domain). "
                               f"Answer precisely. Problem difficulty: {decision.difficulty}." +
                               (" " + pattern_prefix if pattern_prefix else ""))
                model = None
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": problem},
            ]
            try:
                # ProviderLadder.call(model, messages, ...); a per-node model
                # binding overrides the tier default, otherwise the tier name
                # is passed so the ladder picks a live provider model.
                effective = model if model else tier.value
                resp = self.ladder.call(effective, messages,
                                        max_tokens=max_tokens)
            except RuntimeError as e:  # noqa: PERF203
                last = ExecutionResult.__new__(ExecutionResult)
                notes.append({"agent": "provider", "event": "all_providers_failed", "error": str(e)[:200]})
                return self._finalize(last, run_id, problem, decision, "", 0.1, tier,
                                      escalations, notes, t0)
            grade = _grade_answer(problem, resp["content"])
            if matched:
                self.pattern_lib.record(matched[0].name, grade >= self.config.friction.min_confidence)
            self.blackboard.put(f"run:{run_id}:answer", resp["content"], agent="executor")
            if grade >= self.config.friction.min_confidence:
                self.config.budgets.spend(ceo.domain, resp["prompt_tokens"] + resp["completion_tokens"],
                                          resp["cost_usd"])
                if self.org and self.org.active and worker is not None:
                    self.org.note_run(worker.uid, run_id, problem, resp["content"])
                return self._finalize(None, run_id, problem, decision, resp["content"],
                                      min(1.0, grade + 0.1), tier, escalations, notes, t0,
                                      provider=resp["provider"],
                                      model=run_model or resp["model_used"],
                                      pt=resp["prompt_tokens"], ct=resp["completion_tokens"],
                                      usd=resp["cost_usd"])
            notes.append({"agent": "cascade", "event": "grade_low",
                          "grade": grade, "tier": tier.value})
            last_resp = resp
            # escalate
            if escalations >= self.config.friction.max_escalations:
                break
            next_tier = self.TIER_UP[tier]
            if next_tier is None:
                break
            if self.config.budgets.cost_remaining(ceo) <= 0:
                notes.append({"agent": "safety", "event": "cost_ceiling", "tier": tier.value})
                break
            tier = next_tier
            escalations += 1

        # best-effort return of the last attempt
        content = last_resp["content"] if last_resp and "content" in last_resp else ""
        grade = _grade_answer(problem, content)
        if last_resp:
            self.config.budgets.spend(ceo.domain,
                                      last_resp["prompt_tokens"] + last_resp["completion_tokens"],
                                      last_resp["cost_usd"])
        if self.org and self.org.active and worker is not None and content:
            self.org.note_run(worker.uid, run_id, problem, content)
        return self._finalize(None, run_id, problem, decision, content,
                              min(1.0, grade), tier or decision.tier, escalations, notes, t0,
                              provider=(last_resp or {}).get("provider", "none"),
                              model=run_model or (last_resp or {}).get("model_used", "none"),
                              pt=(last_resp or {}).get("prompt_tokens", 0),
                              ct=(last_resp or {}).get("completion_tokens", 0),
                              usd=(last_resp or {}).get("cost_usd", 0.0))

    # ---------------------------------------------------------------
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)

    def _router(self) -> Router:
        if not hasattr(self, "_rt"):
            self._rt = Router(self.config)
        return self._rt

    def _finalize(self, err_result, run_id, problem, decision, content, confidence,
                  tier, escalations, notes, t0, provider="", model="", pt=0, ct=0, usd=0.0):
        r = ExecutionResult(
            run_id=run_id, problem=problem, decision=decision, answer=content,
            confidence=confidence, tier_used=tier, escalations=escalations,
            provider=provider, model_used=model, prompt_tokens=pt,
            completion_tokens=ct, cost_usd=usd, duration_s=time.time() - t0,
            agents_used=1 + escalations, notes=notes)
        self._results.append(r)
        # feed pattern cache outcome (upgrade: real correctness comes from
        # bench_truth ground-truth comparison in Phase E; here we use grade)
        try:
            bucket = f"{decision.problem_type}|{decision.expert}|{decision.difficulty}"
            self._router().cache.record_outcome(bucket, success=confidence >= 0.7)
        except Exception:
            pass
        return r

    @property
    def results(self) -> List[ExecutionResult]:
        return list(self._results)

    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._results)

    def org_summary(self) -> dict:
        """Phase H: summary of the org layer (empty dict when inactive)."""
        return self.org.summary() if self.org else {}
