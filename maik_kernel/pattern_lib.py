"""Pattern Library v0 — the signature invention.

A registry of specialist *patterns* (distilled reasoning styles borrowed or
hand-crafted), each with a routing signature, performance curve, and decay.
The orchestrator hot-swaps patterns at runtime without restarting.

v0 uses hand-crafted adapter patterns (prompt-prefix + tier-hint + weights).
v1 (later) drops in activation-motif distillation artifacts behind the exact
same public API: load()/activate()/deactivate()/performance().
"""

import importlib
import importlib.util
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ModelTier


@dataclass
class PatternSpec:
    """A specialist reasoning pattern."""
    name: str
    signature: str              # routing regex — when this pattern fits
    domain: str                 # which CEO domain it belongs to
    prompt_prefix: str          # injected system prefix when active
    tier_hint: ModelTier        # preferred model tier for this pattern
    extra_weights: Dict[str, float] = field(default_factory=dict)
    version: str = "v0"
    active: bool = True
    hits: int = 0
    success: int = 0
    last_used: float = field(default_factory=time.time)
    load_path: Optional[str] = None   # file it was loaded from (hot-swap)

    def performance(self) -> float:
        """Success rate with decay: untouched patterns decay toward 0.5."""
        if self.hits == 0:
            return 0.5
        raw = self.success / self.hits
        age_hours = (time.time() - self.last_used) / 3600
        decay = max(0.0, 1 - age_hours / 72)  # 72h half-life to baseline
        return raw * 0.7 + 0.5 * decay * 0.3


class PatternLibrary:
    """Registry + hot-swap loader + routing table."""

    def __init__(self, base: Optional[Path] = None):
        _env = os.environ.get("MAIK_DATA_DIR", "")
        self.base = base or (Path(_env) / "patterns" if _env else
                             Path(__file__).resolve().parent.parent / "patterns")
        self.base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.patterns: Dict[str, PatternSpec] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self.register_defaults()

    # -- built-in shipped patterns -----------------------------------------

    def register_defaults(self) -> None:
        defaults = [
            PatternSpec(name="chain_of_thought", signature=r"explain|why|how does",
                        domain="research",
                        prompt_prefix="Think step by step. Show your reasoning "
                                      "before concluding.",
                        tier_hint=ModelTier.SMALL),
            PatternSpec(name="code_reviewer", signature=r"review|audit|bug in|fix",
                        domain="code",
                        prompt_prefix="Act as a senior code reviewer. Identify "
                                      "the bug first, then the minimal fix.",
                        tier_hint=ModelTier.MEDIUM),
            PatternSpec(name="exact_arith", signature=r"\b\d+\s*[x\*+\-/\^]\s*\d+",
                        domain="math",
                        prompt_prefix="Compute exactly. Answer with only the "
                                      "final number.",
                        tier_hint=ModelTier.FLASH),
            PatternSpec(name="debate_verifier", signature=r"verify|check|is it true",
                        domain="review",
                        prompt_prefix="Consider both sides. State the strongest "
                                      "counterargument before your verdict.",
                        tier_hint=ModelTier.SMALL),
            PatternSpec(name="creative_divergent", signature=r"brainstorm|ideas|name",
                        domain="creative",
                        prompt_prefix="Generate 5 distinct options ranging "
                                      "from safe to audacious.",
                        tier_hint=ModelTier.SMALL),
        ]
        with self._lock:
            for p in defaults:
                self.patterns.setdefault(p.name, p)

    # -- public API --------------------------------------------------------

    def register(self, spec: PatternSpec) -> None:
        with self._lock:
            self.patterns[spec.name] = spec

    def deactivate(self, name: str) -> None:
        with self._lock:
            if name in self.patterns:
                self.patterns[name].active = False

    def activate(self, name: str) -> None:
        with self._lock:
            if name in self.patterns:
                self.patterns[name].active = True

    def hot_swap(self, name: str, new_prefix: str,
                 new_tier: Optional[ModelTier] = None) -> Optional[PatternSpec]:
        """Update a pattern in place — <1ms, no restart."""
        with self._lock:
            spec = self.patterns.get(name)
            if spec is None:
                return None
            spec.prompt_prefix = new_prefix
            if new_tier:
                spec.tier_hint = new_tier
            return spec

    def load_from_file(self, path: Path) -> Optional[PatternSpec]:
        """Load a pattern spec from a JSON/Python adapter file — hot-swap in.

        JSON: {"name", "signature", "domain", "prompt_prefix", "tier_hint",
               "extra_weights"}
        Python adapter: defines get_spec() -> dict with the same keys.
        """
        text = path.read_text()
        if path.suffix == ".json":
            d = json.loads(text)
        else:
            mod_name = "pat_" + re.sub(r"\W", "_", path.stem)
            if mod_name in self._loaded_modules:
                importlib.reload(self._loaded_modules[mod_name])
            else:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self._loaded_modules[mod_name] = mod
            d = mod.get_spec()
        spec = PatternSpec(name=d["name"], signature=d["signature"],
                           domain=d["domain"], prompt_prefix=d["prompt_prefix"],
                           tier_hint=ModelTier(d.get("tier_hint", "small")),
                           extra_weights=d.get("extra_weights", {}),
                           version=d.get("version", "v0"),
                           load_path=str(path))
        with self._lock:
            self.patterns[spec.name] = spec
        return spec

    def match(self, problem: str) -> List[PatternSpec]:
        """Routing table: which active patterns fit this problem."""
        text = problem.lower()
        with self._lock:
            matched = [p for p in self.patterns.values()
                       if p.active and re.search(p.signature, text)]
        matched.sort(key=lambda p: -p.performance())
        return matched

    def record(self, name: str, success: bool) -> None:
        with self._lock:
            p = self.patterns.get(name)
            if p is None:
                return
            p.hits += 1
            p.success += 1 if success else 0
            p.last_used = time.time()

    def status(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"name": p.name, "domain": p.domain, "active": p.active,
                 "performance": round(p.performance(), 3), "hits": p.hits,
                 "tier_hint": p.tier_hint.value, "version": p.version}
                for p in self.patterns.values()
            ]
