"""API & Model Management Agent (Phase K).

The agent whose entire job is taking care of MAIK's APIs and models:

  - per-node budgets (tokens AND dollars) with tripwires at 80%
  - per-provider rate limits (calls/minute + burst) enforced client-side
  - automatic fallback switching: when a provider burns through its rate
    limit or starts erroring, the department reroutes its nodes to the
    next live provider in the ladder
  - live cost monitoring: dashboard of spend, per-node spend, remaining
    budgets, and circuit-breaker states

The CEO asks this agent "how are our APIs doing?" and gets a single
truthful answer — before any money is spent, not after.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .live_execution import LiveExecution
from .providers import COST_PER_1M, ProviderEntry


@dataclass
class NodeQuota:
    node_uid: str
    node_name: str
    token_budget: int = 100_000
    usd_budget: float = 0.01   # default safety cap per node per day
    tokens_used: int = 0
    usd_used: float = 0.0


@dataclass
class ProviderLimit:
    provider: str
    calls_per_minute: int = 30
    burst: int = 5
    calls_recorded: List[float] = field(default_factory=list)


class ApiManagement:
    """The API department: quotas, rate limits, fallbacks, monitoring."""

    def __init__(self, live: Optional[LiveExecution] = None):
        self.live = live or LiveExecution()
        self._quotas: Dict[str, NodeQuota] = {}
        self._limits: Dict[str, ProviderLimit] = {
            "openrouter_free": ProviderLimit("openrouter_free", 20, 4),
            "openai": ProviderLimit("openai", 3000, 100),
            "anthropic": ProviderLimit("anthropic", 1000, 50),
            "google": ProviderLimit("google", 1000, 60),
            "free_gateway": ProviderLimit("free_gateway", 60, 10),
            "local_gateway": ProviderLimit("local_gateway", 1000, 100),
            "stub": ProviderLimit("stub", 10000, 500),
        }
        self._spend_log: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------ quotas
    def set_quota(self, node_uid: str, node_name: str,
                  token_budget: Optional[int] = None,
                  usd_budget: Optional[float] = None) -> dict:
        with self._lock:
            q = self._quotas.get(node_uid)
            if q is None:
                q = NodeQuota(node_uid, node_name)
                self._quotas[node_uid] = q
            if token_budget is not None:
                q.token_budget = token_budget
            if usd_budget is not None:
                q.usd_budget = usd_budget
            return {"node": node_name, "token_budget": q.token_budget,
                    "usd_budget": q.usd_budget}

    def record_spend(self, node_uid: str, provider: str,
                     tokens: int, usd: float) -> dict:
        """Record a call's spend against the node quota and provider limit."""
        with self._lock:
            q = self._quotas.setdefault(node_uid,
                                        NodeQuota(node_uid, node_uid))
            q.tokens_used += max(0, tokens)
            q.usd_used += max(0.0, usd)
            self._spend_log.append({"node": node_uid, "provider": provider,
                                    "tokens": tokens, "usd": usd,
                                    "ts": time.time()})
            lim = self._limits.setdefault(provider,
                                          ProviderLimit(provider))
            now = time.time()
            lim.calls_recorded = [t for t in lim.calls_recorded
                                  if now - t < 60]
            allowed = (lim.calls_recorded[-lim.burst:]
                       if len(lim.calls_recorded) >= lim.burst
                       else lim.calls_recorded)
            under_burst = (len(lim.calls_recorded) < lim.burst or
                           now - allowed[0] >= 60)
            under_rpm = len(lim.calls_recorded) < lim.calls_per_minute
            lim.calls_recorded.append(now)
            if not (under_burst and under_rpm):
                return {"allowed": False, "reason": "rate_limit"}
            over_pct = (q.usd_used / q.usd_budget) if q.usd_budget else 0
            over_tokens = q.tokens_used > q.token_budget
            if over_pct >= 1.0 or over_tokens:
                return {"allowed": False,
                        "reason": "usd_over" if over_pct >= 1.0 else "tokens_over"}
            return {"allowed": True,
                    "warning": "approaching_usd_budget" if over_pct >= 0.8
                    else (None)}

    # ------------------------------------------------------------ fallbacks
    def fallback_report(self) -> dict:
        """Which providers are stressed (circuit open or rate-limited) and
        which nodes would need to reroute."""
        status = self.live.ladder.status()
        stressed = [s["provider"] for s in status
                    if s["circuit"] == "open" or not s["enabled"]]
        lim_hits = [p for p, l in self._limits.items()
                    if len(l.calls_recorded) >= l.calls_per_minute]
        return {"stressed_providers": stressed,
                "rate_saturated": lim_hits,
                "healthy_providers": [s["provider"] for s in status
                                      if s["circuit"] == "closed"
                                      and s["enabled"]],
                "reroute_advice": "switch stressed nodes to healthy "
                                  "providers" if (stressed or lim_hits) else
                "all clear"}

    # ------------------------------------------------------------ dashboard
    def dashboard(self) -> dict:
        with self._lock:
            now = time.time()
            day = [e for e in self._spend_log if now - e["ts"] < 86400]
            quota_rows = []
            for q in self._quotas.values():
                quota_rows.append({
                    "node": q.node_name,
                    "tokens_used_pct": round(100 * q.tokens_used /
                                             q.token_budget, 1)
                    if q.token_budget else 0,
                    "usd_used": round(q.usd_used, 6),
                    "usd_budget": q.usd_budget,
                    "usd_pct": round(100 * (q.usd_used / q.usd_budget), 1)
                    if q.usd_budget else 0,
                    "tripwire": q.usd_used >= 0.8 * q.usd_budget
                    if q.usd_budget else False,
                })
            return {
                "nodes": quota_rows,
                "day_total_usd": round(sum(e["usd"] for e in day), 6),
                "day_total_tokens": sum(e["tokens"] for e in day),
                "calls_day": len(day),
                "providers": self.live.ladder.status(),
                "fallback": self.fallback_report(),
            }

    # ------------------------------------------------------------ estimates
    def estimate_cost(self, model_hint: str, prompt_tokens: int,
                      completion_tokens: int) -> float:
        for hint, (pin, pout) in COST_PER_1M.items():
            if hint in model_hint:
                return round((pin * prompt_tokens + pout * completion_tokens)
                             / 1_000_000, 6)
        return 0.0
