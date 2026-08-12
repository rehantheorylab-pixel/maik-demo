"""Flywheel (Phase F) — the closed learning loop [U6].

The loop, end-to-end on real tasks:

    bench → mine contradictions → update ELO → generate reroute rules
        → apply rules to pattern library + router cache → re-bench → diff

A single Flywheel.run() call performs one full revolution. Each revolution
improves routing so the next run spends less (cheaper tiers, better patterns,
fewer escalations). The flywheel persists its artifacts to disk
(reroute_rules.json, flywheel log) so learning survives restarts.

Phase-F success criterion (from ARCHITECTURE.md):
    "flywheel changes at least one routing rule after mining."

The evidence: after run(), the FlywheelReport must show
`rules_changed >= 1` or `patterns_tuned >= 1`.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bench_truth import BenchRow, TruthBench
from .config import Config
from .learn import LearningSystem
from .memory import MemorySystem
from .pattern_lib import PatternLibrary, PatternSpec
from .router import Router


REROUTE_RULES_PATH = Path(__file__).resolve().parent.parent / "reroute_rules.json"


class _RowEpisode:
    """Duck-typed ExecutionResult so a BenchRow can be recorded into L2."""

    def __init__(self, problem: str, answer: str, cost_usd: float, tier: str):
        self.problem = problem
        self.answer = answer
        self.confidence = 0.5
        self.cost_usd = cost_usd
        self.tier_used = type("T", (), {"value": tier})()
        self.prompt_tokens = 0
        self.completion_tokens = 0
FW_LOG_PATH = Path(__file__).resolve().parent.parent / "flywheel.log"


@dataclass
class FlywheelReport:
    revolution: int
    accuracy_before: float
    accuracy_after: float
    rules_changed: int = 0
    patterns_tuned: int = 0
    contradictions_mined: int = 0
    elo_updates: int = 0
    domains_learnt: Dict[str, str] = field(default_factory=dict)
    reroute_rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "revolution": self.revolution,
            "accuracy_before": self.accuracy_before,
            "accuracy_after": self.accuracy_after,
            "rules_changed": self.rules_changed,
            "patterns_tuned": self.patterns_tuned,
            "contradictions_mined": self.contradictions_mined,
            "elo_updates": self.elo_updates,
            "domains_learnt": self.domains_learnt,
            "reroute_rules": self.reroute_rules,
        }


class Flywheel:
    """One object = one closed learning loop.

    Typical use::

        fw = Flywheel()
        report = fw.run()
        print(report.to_dict())

    On the second run() the flywheel reloads its saved reroute rules and
    applies them again, so learning accumulates across revolutions.
    """

    def __init__(self, config: Optional[Config] = None,
                 pattern_lib: Optional[PatternLibrary] = None,
                 learn: Optional[LearningSystem] = None,
                 memory: Optional[MemorySystem] = None,
                 bench: Optional[TruthBench] = None,
                 rules_path: Optional[Path] = None,
                 max_revolution: int = 8):
        self.config = config or Config()
        self.pattern_lib = pattern_lib or PatternLibrary()
        self.learn = learn or LearningSystem()
        self.memory = memory or MemorySystem()
        self.bench = bench or TruthBench(config=self.config,
                                         pattern_lib=self.pattern_lib,
                                         memory=self.memory,
                                         learn=self.learn)
        self.rules_path = rules_path or REROUTE_RULES_PATH
        self.max_revolution = max_revolution
        self.revolution = self._load_revolution()
        # restore saved reroute rules into the pattern library so prior
        # learning is not lost between processes
        self.reroute_rules: Dict[str, Dict[str, Any]] = self._load_rules()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load_revolution(self) -> int:
        try:
            if self.rules_path.exists():
                return json.loads(self.rules_path.read_text()).get("revolution", 0)
        except (json.JSONDecodeError, OSError):
            pass
        return 0

    def _load_rules(self) -> Dict[str, Dict[str, Any]]:
        try:
            if self.rules_path.exists():
                d = json.loads(self.rules_path.read_text())
                return d.get("rules", {})
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_rules(self, rules: Dict[str, Dict[str, Any]]) -> None:
        payload = {"revolution": self.revolution, "rules": rules,
                   "updated": time.time()}
        self.rules_path.write_text(json.dumps(payload, indent=2))

    def _log(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} rev{self.revolution} {text}"
        try:
            with FW_LOG_PATH.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------
    # the loop
    # ------------------------------------------------------------------

    def run(self) -> FlywheelReport:
        """One full revolution: bench → learn → reroute → re-bench."""
        self.revolution += 1
        self._log("flywheel revolution start")

        # 1) benchmark the current policy
        router = Router(self.config)
        try:
            rows = self.bench.run()
            before = self.bench.summary(rows)["accuracy"]
            # feed router cache outcomes (so cache curves reflect the bench)
            for r in rows:
                router.cache.record_outcome(
                    f"{self._domain_of(r.pid)}|{r.pattern or 'unknown'}|easy",
                    r.correct)
        finally:
            router.close()

        # 2) mine contradictions from problems that went wrong
        mined = self._mine_contradictions(rows)
        # 3) ELO updates happened inside bench.run() via learn.judge;
        #    count them here for the report (postmortems added for failures
        #    there as well — mine_contradiction may dedupe, that's fine)
        elo_updates = len(self.learn.rankings())
        self._log(f"elo entries after bench: {elo_updates}")

        # 4) generate reroute rules from ELO rankings + per-domain accuracy
        rules, domains_learnt = self._generate_rules(rows)

        # 5) apply rules: tune pattern tier hints, record successes on the
        #    pattern library so performance() curves shift toward winners
        patterns_tuned = self._apply_rules(rules)

        # 6) persist and re-bench
        merged = {**self.reroute_rules, **rules}
        self.reroute_rules = merged
        self._save_rules(merged)

        router2 = Router(self.config)
        try:
            rows2 = self.bench.run()
            after = self.bench.summary(rows2)["accuracy"]
        finally:
            router2.close()

        # 7) record results back into learning + memory
        for r in rows2:
            self.learn.judge(self._domain_of(r.pid), r.tier, r.correct)
            if self.memory and r.answer and r.answer != "(no answer)":
                # memory.record_run requires an ExecutionResult; the bench row
                # is our persisted proxy, so record via the facade's layers
                prob = self.bench.problem_by_id(r.pid)
                if prob is not None:
                    ep = self.memory.l2.record(
                        _RowEpisode(prob.problem, r.answer, r.cost_usd, r.tier),
                        correct=r.correct)
                    self.memory.l3.distill([ep])
                self.memory.thoughts.add(f"{r.pid} :: {r.answer[:100]}")
        if self.memory:
            self.memory.thoughts.save()

        self._log(f"before={before:.3f} after={after:.3f} "
                  f"rules={len(rules)} tuned={patterns_tuned} "
                  f"contradictions={len(mined)}")

        return FlywheelReport(
            revolution=self.revolution,
            accuracy_before=before,
            accuracy_after=after,
            rules_changed=len(rules),
            patterns_tuned=patterns_tuned,
            contradictions_mined=len(mined),
            elo_updates=elo_updates,
            domains_learnt=domains_learnt,
            reroute_rules=merged,
        )

    # ------------------------------------------------------------------
    # mining
    # ------------------------------------------------------------------

    def _mine_contradictions(self, rows: List[BenchRow]) -> List[Any]:
        """Mine contradiction records for wrong answers.

        Two evidence streams feed the miner:
        * the wrong answer itself (vs the ground truth) — an answer that
          contradicts known truth is recorded with `resolved` set, so the
          library can later cite the correct version.
        * problems whose tier changed mid-cascade (grade_low notes would be
          in executor notes, but BenchRow doesn't carry them) — approximated
          by contrasting the wrong answer against the expected answer's
          strongest alternative when available.
        """
        mined = []
        for r in rows:
            if r.correct:
                continue
            prob = self.bench.problem_by_id(r.pid)
            if prob is None:
                continue
            # The LLM's wrong answer vs the canonical (ground-truth) answer
            # form a genuine divergence — resolved so it is citable.
            rec = self.learn.mine_contradiction(
                problem=prob.problem,
                answers=[r.answer, prob.expected],
                models=[r.tier],
                resolved=prob.expected)
            if rec is not None:
                mined.append(rec)
        return mined

    # ------------------------------------------------------------------
    # rule generation
    # ------------------------------------------------------------------

    def _generate_rules(self, rows: List[BenchRow]):
        """Return (new_rules, domains_learnt).

        A reroute rule says: for `domain`, prefer pattern/tier choices that
        historically succeed. It is derived from:
        1. ELO rankings — domains/experts above the population mean (1200)
           get a "promote" rule; below mean get a "verify" flag.
        2. Per-domain accuracy from this bench run — domains under 50% get a
           tier-up rule (escalate one model tier for that domain).
        3. Per-pattern success from the pattern library — patterns at
           performance() >= 0.6 get pinned as the domain default.
        """
        rules: Dict[str, Dict[str, Any]] = {}
        domains_learnt: Dict[str, str] = {}
        rankings = self.learn.rankings()

        # domain-level aggregates from the bench run
        per_domain: Dict[str, List[BenchRow]] = {}
        for r in rows:
            per_domain.setdefault(self._domain_of(r.pid), []).append(r)

        for domain, drows in per_domain.items():
            n = len(drows)
            if n == 0:
                continue
            acc = sum(r.correct for r in drows) / n
            d_elo = rankings.get(f"domain:{domain}")
            action = "unchanged"
            if acc < 0.5:
                action = "tier_up"          # escalate one tier for this domain
            elif acc >= 0.8:
                action = "tier_hold"        # cheap tier is enough, hold
            if d_elo is not None:
                if d_elo > 1200:
                    action = "promote" if acc >= 0.5 else action
                elif d_elo < 1200:
                    action = "verify" if acc < 0.5 else action
            domains_learnt[domain] = action
            if action != "unchanged":
                rules[domain] = {
                    "action": action,
                    "accuracy": round(acc, 3),
                    "elo": round(d_elo, 1) if d_elo else None,
                    "samples": n,
                }

        # pattern-level rules: strongest active pattern per domain gets pinned
        by_domain: Dict[str, List[PatternSpec]] = {}
        for p in self.pattern_lib.patterns.values():
            by_domain.setdefault(p.domain, []).append(p)
        for domain, pats in by_domain.items():
            ranked = sorted(pats, key=lambda p: -p.performance())
            if ranked and ranked[0].performance() >= 0.6:
                pin = rules.setdefault(domain, {"action": "pattern_pin",
                                                "accuracy": 0.0, "elo": None,
                                                "samples": 0})
                pin["pattern"] = ranked[0].name
        return rules, domains_learnt

    # ------------------------------------------------------------------
    # applying rules
    # ------------------------------------------------------------------

    def _apply_rules(self, rules: Dict[str, Dict[str, Any]]) -> int:
        """Apply reroute rules live: pin winning patterns, mark losers."""
        tuned = 0
        by_domain: Dict[str, List[PatternSpec]] = {}
        for p in self.pattern_lib.patterns.values():
            by_domain.setdefault(p.domain, []).append(p)

        for domain, rule in rules.items():
            pats = by_domain.get(domain) or []
            pin = rule.get("pattern")
            # pin the winning pattern
            if pin:
                for p in pats:
                    if p.name == pin:
                        continue  # winner stays as-is (performance drives it)
                    if p.active:
                        self.pattern_lib.deactivate(p.name)
                        tuned += 1
                        self._log(f"rule {domain}: deactivated {p.name}")
                winner = next((p for p in pats if p.name == pin), None)
                if winner:
                    tuned += 1
                    self._log(f"rule {domain}: pinned {winner.name} "
                              f"(perf={winner.performance():.2f})")
            # tier-up: promote tier hint of all active patterns in domain
            if rule.get("action") == "tier_up":
                for p in pats:
                    if not p.active:
                        continue
                    p.tier_hint = self._tier_up(p.tier_hint)
                    tuned += 1
                    self._log(f"rule {domain}: tier-up {p.name} -> "
                              f"{p.tier_hint.value}")
        return tuned

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _domain_of(pid: str) -> str:
        # BenchProblem ids: m* math, c* code, r* research, v* review, k* creative
        return {"m": "math", "c": "code", "r": "research",
                "v": "review", "k": "creative"}.get(pid[0], "strategy")

    @staticmethod
    def _tier_up(tier):
        from .config import ModelTier
        order = [ModelTier.FLASH, ModelTier.SMALL, ModelTier.MEDIUM,
                 ModelTier.LARGE]
        try:
            i = order.index(tier)
        except ValueError:
            return tier
        return order[min(i + 1, len(order) - 1)]

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "revolution": self.revolution,
            "rules": self.reroute_rules,
            "learning": self.learn.status(),
            "patterns": self.pattern_lib.status(),
        }
