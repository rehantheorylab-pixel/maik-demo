"""Executive Council configuration — the governance skeleton.

Kept from maik-demo v2 (audit-verified): 12 CEOs, per-CEO token budgets,
friction dial, model tiers. Upgrades: cost limits per CEO ($/task),
config hot-reload hook, freeze mode for benchmark runs.
"""

import copy
import enum
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


class ModelTier(enum.Enum):
    FLASH = "flash"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

    @classmethod
    def all(cls) -> List["ModelTier"]:
        return [c for c in cls]


# Example models per tier — resolved to actual provider models in providers.py
TIER_MODELS = {
    ModelTier.FLASH: ["gemini/gemini-2.0-flash-lite-001", "openrouter/auto:gemini-2.0-flash-lite"],
    ModelTier.SMALL: ["openrouter/qwen/qwen-3-4b", "openrouter/auto:gemini-2.0-flash"],
    ModelTier.MEDIUM: ["openrouter/qwen/qwen-3-8b", "openrouter/deepseek/deepseek-chat-v3-0324:free"],
    ModelTier.LARGE: ["openrouter/deepseek/deepseek-r1:free", "openrouter/google/gemini-2.5-flash"],
}


@dataclass
class CEOProfile:
    name: str
    domain: str
    experts: List[str]
    default_tier: ModelTier
    budget_tokens: int = 60_000
    cost_limit_usd: float = 0.05  # upgrade U3: $/task ceiling


@dataclass
class BudgetLedger:
    """Per-CEO token and cost tracking with tripwires."""
    spent: Dict[str, int] = field(default_factory=dict)
    cost_spent: Dict[str, float] = field(default_factory=dict)
    _lock = threading.Lock()

    def spend(self, ceo_key: str, tokens: int, usd: float = 0.0) -> None:
        with self._lock:
            self.spent[ceo_key] = self.spent.get(ceo_key, 0) + max(0, tokens)
            self.cost_spent[ceo_key] = self.cost_spent.get(ceo_key, 0.0) + max(0.0, usd)

    def remaining(self, ceo: CEOProfile) -> int:
        return max(0, ceo.budget_tokens - self.spent.get(ceo.domain, 0))

    def cost_remaining(self, ceo: CEOProfile) -> float:
        return max(0.0, ceo.cost_limit_usd - self.cost_spent.get(ceo.domain, 0.0))

    def warn_pct(self, ceo: CEOProfile) -> float:
        spent = self.spent.get(ceo.domain, 0)
        return spent / ceo.budget_tokens if ceo.budget_tokens else 0.0

    def breakdown(self, council: List[CEOProfile]) -> Dict[str, dict]:
        out = {}
        for c in council:
            spent = self.spent.get(c.domain, 0)
            out[c.domain] = {
                "name": c.name,
                "spent_tokens": spent,
                "remaining_tokens": c.budget_tokens - spent,
                "budget_tokens": c.budget_tokens,
                "used_pct": round(100 * spent / c.budget_tokens, 1) if c.budget_tokens else 0,
                "cost_spent_usd": round(self.cost_spent.get(c.domain, 0.0), 6),
                "cost_limit_usd": c.cost_limit_usd,
            }
        return out


class ProfileMode(enum.Enum):
    LIGHT = "light"   # 2 CEOs (fast demos)
    FULL = "full"     # 12 CEOs (production)


def _default_ceos() -> List[CEOProfile]:
    return [
        CEOProfile("Chief Strategy", "strategy", ["planner", "decomposer"], ModelTier.SMALL, 50_000),
        CEOProfile("Chief Code", "code", ["code_writer", "code_reviewer", "debugger"], ModelTier.SMALL, 80_000),
        CEOProfile("Chief Math", "math", ["math_solver", "prover"], ModelTier.FLASH, 40_000),
        CEOProfile("Chief Research", "research", ["explorer", "synthesizer", "summarizer"], ModelTier.FLASH, 60_000),
        CEOProfile("Chief Exploration", "exploration", ["scout", "curator"], ModelTier.SMALL, 50_000),
        CEOProfile("Chief Security", "security", ["security_auditor", "vuln_checker"], ModelTier.MEDIUM, 30_000),
        CEOProfile("Chief Synthesis", "synthesis", ["integrator", "writer"], ModelTier.SMALL, 40_000),
        CEOProfile("Chief Planning", "planning", ["scheduler", "executor"], ModelTier.FLASH, 40_000),
        CEOProfile("Chief Data", "data", ["analyst", "visualizer"], ModelTier.SMALL, 50_000),
        CEOProfile("Chief Creative", "creative", ["brainstormer", "designer"], ModelTier.SMALL, 40_000),
        CEOProfile("Chief Review", "review", ["verifier", "critic"], ModelTier.FLASH, 40_000),
        CEOProfile("Chief Ops", "ops", ["orchestrator", "monitor"], ModelTier.FLASH, 30_000),
    ]


class FrictionDial:
    """0 (fastest, most risk) -> 10 (safest, most verification).

    Maps monotonically to min_confidence and max agent-tree depth.
    """

    _table = [  # dial -> (min_confidence, max_depth, cascade_max_esc)
        (0.30, 4, 2), (0.37, 4, 2), (0.44, 4, 2), (0.51, 4, 2), (0.58, 4, 2),
        (0.65, 4, 2), (0.70, 3, 2), (0.77, 3, 2), (0.84, 3, 2), (0.90, 2, 2),
        (0.95, 2, 2),
    ]

    def __init__(self, dial: int = 5):
        self.dial = max(0, min(10, int(dial)))

    @property
    def min_confidence(self) -> float:
        return self._table[self.dial][0]

    @property
    def max_depth(self) -> int:
        return self._table[self.dial][1]

    @property
    def max_escalations(self) -> int:
        return self._table[self.dial][2]

    def set(self, dial: int) -> None:
        self.dial = max(0, min(10, int(dial)))


class ConfigError(ValueError):
    pass


class Config:
    """Top-level MAIK config. Immutable-ish during benchmark runs (freeze mode)."""

    def __init__(self, mode: ProfileMode = ProfileMode.FULL, friction: int = 5,
                 ceos: Optional[List[CEOProfile]] = None):
        self.version = "3.0.0"
        self.mode = mode
        self.friction = FrictionDial(friction)
        self._ceos = ceos if ceos is not None else _default_ceos()
        self.budgets = BudgetLedger()
        self._frozen = False
        self._change_hooks: List[Callable] = []

    # -- council ---------------------------------------------------------
    @property
    def ceos(self) -> List[CEOProfile]:
        if self.mode == ProfileMode.LIGHT:
            # light mode: keep only Code + Research (broadest coverage)
            keep = {"code", "research"}
            return [c for c in self._ceos if c.domain in keep] or self._ceos[:2]
        return self._ceos

    def ceo_for_domain(self, domain: str) -> Optional[CEOProfile]:
        for c in self._ceos:
            if c.domain == domain:
                return c
        # best-effort: match any expert membership
        for c in self._ceos:
            if domain in c.experts:
                return c
        return None

    def council_breakdown(self) -> dict:
        return {
            "mode": self.mode.value,
            "num_ceos": len(self.ceos),
            "friction": self.friction.dial,
            "min_confidence": self.friction.min_confidence,
            "budgets": self.budgets.breakdown(self.ceos),
        }

    # -- hot reload ------------------------------------------------------
    def on_change(self, hook: Callable) -> None:
        if self._frozen:
            raise ConfigError("Config is frozen (benchmark run in progress)")
        self._change_hooks.append(hook)

    def set_friction(self, dial: int) -> None:
        if self._frozen:
            raise ConfigError("Config is frozen")
        self.friction.set(dial)
        for h in self._change_hooks:
            try:
                h(self)
            except Exception:
                pass

    def freeze(self) -> None:
        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    # -- persistence -----------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "mode": self.mode.value,
            "friction": self.friction.dial,
            "ceos": [
                {"name": c.name, "domain": c.domain, "experts": c.experts,
                 "default_tier": c.default_tier.value,
                 "budget_tokens": c.budget_tokens,
                 "cost_limit_usd": c.cost_limit_usd}
                for c in self._ceos
            ],
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Config":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid config JSON: {e}")
        if d.get("version") != "3.0.0":
            raise ConfigError(f"Unsupported config version: {d.get('version')}")
        mode = ProfileMode(d.get("mode", "full"))
        ceos = [
            CEOProfile(c["name"], c["domain"], c["experts"],
                       ModelTier(c.get("default_tier", "small")),
                       c.get("budget_tokens", 60_000),
                       c.get("cost_limit_usd", 0.05))
            for c in d.get("ceos", [])
        ]
        if not ceos:
            raise ConfigError("Config has no CEOs")
        dial = d.get("friction", 5)
        if not (0 <= dial <= 10):
            raise ConfigError(f"Friction dial out of range: {dial}")
        cfg = cls(mode=mode, friction=dial, ceos=ceos)
        cfg.validate()
        return cfg

    def validate(self) -> List[str]:
        issues = []
        if len(self._ceos) < 2:
            issues.append("At least 2 CEOs required")
        for c in self._ceos:
            if c.budget_tokens <= 0:
                issues.append(f"CEO {c.domain}: non-positive budget")
            if c.cost_limit_usd < 0:
                issues.append(f"CEO {c.domain}: negative cost limit")
            if c.default_tier not in ModelTier:
                issues.append(f"CEO {c.domain}: unknown tier {c.default_tier}")
        if issues:
            raise ConfigError("; ".join(issues))
        return issues

    @classmethod
    def load(cls, path: Path) -> "Config":
        return cls.from_json(Path(path).read_text())

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json())
