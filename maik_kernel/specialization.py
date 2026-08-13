"""MAIK v3.4.0 — The Specialization Layer.

The swarm-of-specialists principle: many specialized AIs, each proven best at
one feature, working together under orchestration, beat a single generalist
monolith on average — and they do it at a fraction of the cost.

This module provides:

- ``Domain`` taxonomy (math, code, reasoning, research, creative, verification,
  frontend, security) — the "one feature per specialist" map.
- ``SpecializationMatrix`` — evidence-based binding of domains to models. The
  CEO (or the benchmark) records which model wins which domain; routing reads
  from it. Beating ``BindingStore`` (per-node) with per-domain knowledge.
- ``SpecializationBench`` — runs the same ground-truth problem set through
  multiple candidate models and records who wins each domain, writing the
  evidence into the matrix. This is how the swarm learns its own roster.
- ``compare_report`` — formats the matrix as an evidence table usable in
  README/reports, including head-to-head framing.

Every claim this module makes is backed by a row of benchmark evidence —
never by marketing language.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Domain taxonomy — one feature per specialist
# ---------------------------------------------------------------------------

DOMAINS = [
    "math",
    "code",
    "reasoning",
    "research",
    "creative",
    "verification",
    "frontend",
    "security",
]


@dataclass
class DomainResult:
    """Evidence for one model on one domain."""

    model: str
    domain: str
    problems: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    avg_seconds: float = 0.0
    evidence_ids: List[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.problems if self.problems else 0.0


# ---------------------------------------------------------------------------
# Specialization matrix — evidence-based domain → model map
# ---------------------------------------------------------------------------

class SpecializationMatrix:
    """Which model is proven best for which domain, with evidence attached.

    Persisted to ``MAIK_DATA_DIR/specialization.json`` (when the env is set).
    """

    def __init__(self, base: Optional[Path] = None) -> None:
        self._base = base
        self._data: Dict[str, DomainResult] = {}
        self._path = (self._base or Path.cwd()) / "specialization.json"
        self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                self._data = {k: DomainResult(**v) for k, v in raw.items()}
            except (json.JSONDecodeError, TypeError, KeyError):
                self._data = {}

    def save(self) -> None:
        if self._base is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(
            {k: asdict(v) for k, v in self._data.items()}, indent=2))

    # -- evidence -----------------------------------------------------------

    def record(self, model: str, domain: str, passed: int, total: int,
               cost_usd: float = 0.0, tokens: int = 0, seconds: float = 0.0,
               evidence_ids: Optional[List[str]] = None) -> DomainResult:
        key = f"{model}::{domain}"
        dr = self._data.get(key, DomainResult(model=model, domain=domain))
        dr.problems += total
        dr.correct += passed
        dr.total_cost_usd += cost_usd
        dr.total_tokens += tokens
        dr.avg_seconds = ((dr.avg_seconds * (dr.problems - total))
                          + seconds * total) / dr.problems if dr.problems else 0
        dr.evidence_ids += evidence_ids or []
        self._data[key] = dr
        self.save()
        return dr

    def get(self, model: str, domain: str) -> Optional[DomainResult]:
        return self._data.get(f"{model}::{domain}")

    # -- routing ------------------------------------------------------------

    def best_for(self, domain: str, min_problems: int = 1) -> Optional[str]:
        """Model with highest proven accuracy for a domain (enough evidence)."""
        candidates = [v for v in self._data.values()
                      if v.domain == domain and v.problems >= min_problems]
        if not candidates:
            return None
        candidates.sort(key=lambda v: (-v.accuracy, v.avg_seconds))
        return candidates[0].model

    def ranked(self, domain: str, min_problems: int = 1) -> List[DomainResult]:
        return sorted([v for v in self._data.values()
                       if v.domain == domain and v.problems >= min_problems],
                      key=lambda v: (-v.accuracy, v.avg_seconds))

    def domains_covered(self) -> List[str]:
        return sorted({v.domain for v in self._data.values()})

    # -- comparison ---------------------------------------------------------

    def swarm_score(self, min_problems: int = 1) -> Dict[str, Any]:
        """Average best-specialist accuracy across covered domains."""
        covered = self.domains_covered()
        scores = []
        for dom in covered:
            best = self.best_for(dom, min_problems)
            if best:
                scores.append(self._data[f"{best}::{dom}"].accuracy)
        return {
            "domains_covered": len(covered),
            "swarm_avg_accuracy": (sum(scores) / len(scores)) if scores else 0.0,
            "per_domain_best": {d: self.best_for(d, min_problems)
                                for d in covered},
        }

    def summary(self) -> dict:
        rows = [asdict(v) for v in self._data.values()]
        return {"entries": len(rows), "data": rows}


# ---------------------------------------------------------------------------
# Specialization benchmark — prove who wins what, live
# ---------------------------------------------------------------------------

class SpecializationBench:
    """Run a problem set through several candidate models and record which
    model wins which domain — the evidence behind the swarm roster."""

    def __init__(self, matrix: SpecializationMatrix,
                 executor=None, bench=None):
        self.matrix = matrix
        self._executor = executor
        self._bench = bench

    def run(self, models: List[str], problems: Optional[list] = None,
            domain_of: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute each model against each problem and record domain wins."""
        from maik_kernel.bench_truth import TruthBench  # local import

        bench = self._bench or TruthBench()
        procs = problems or bench.problems

        if domain_of is None:
            domain_of = {p.id: p.domain for p in procs}

        results: Dict[str, Dict[str, DomainResult]] = {}
        rows = []

        for model in models:
            results[model] = {}
            for prob in procs:
                dom = domain_of.get(prob.id, prob.domain)
                try:
                    res = self._executor.execute(
                            prob.problem, model_override=model)
                    answer = (res.answer or "").strip()
                    judge_ok = bench._judge(prob, answer) if answer else False
                    tokens = res.prompt_tokens + res.completion_tokens
                    cost = res.cost_usd or 0.0
                except Exception:  # noqa: BLE001
                    answer, judge_ok, tokens, cost = "", False, 0, 0.0
                dr = self.matrix.record(
                    model=model, domain=dom,
                    passed=1 if judge_ok else 0, total=1,
                    cost_usd=cost, tokens=tokens,
                    evidence_ids=[prob.id])
                results[model][prob.id] = dr
                rows.append({"model": model, "pid": prob.id,
                             "domain": dom, "ok": judge_ok,
                             "answer": answer[:120]})

        self.matrix.save()
        return {"rows": rows, "matrix": self.matrix.summary(),
                "swarm": self.matrix.swarm_score()}


def compare_report(matrix: SpecializationMatrix, rivals: Optional[Dict[str,
                            dict]] = None) -> str:
    """Format the evidence matrix as a readable report; ``rivals`` is a dict of
    model → dict(capabilities, weaknesses, price) pulled from public sources
    so head-to-head claims are sourced, not invented."""
    lines = ["# MAIK Specialization Report",
             "",
             "Evidence gathered from live benchmark runs. Rows below are",
             "recorded per model per domain — no claim is made without a row.",
             ""]
    covered = matrix.domains_covered()
    if not covered:
        lines.append("No specialization evidence recorded yet. "
                     "Run `maik bench specialists` first.")
        return "\n".join(lines)

    lines.append("| Domain | Best proven model | Accuracy | "
                 "Avg latency (s) |")
    lines.append("|---|---|---|---|")
    for dom in covered:
        for dr in matrix.ranked(dom):
            flag = " ← swarm pick" if dr.model == matrix.best_for(dom) else ""
            lines.append(f"| {dom} | {dr.model} | "
                         f"{dr.accuracy:.1%} | {dr.avg_seconds:.1f}{flag} |")

    sc = matrix.swarm_score()
    lines += ["",
              f"Swarm average accuracy across {sc['domains_covered']} domains: "
              f"{sc['swarm_avg_accuracy']:.1%}",
              ""]
    if rivals:
        lines.append("## Sourced rival framing (public information only)")
        lines.append("")
        for name, info in rivals.items():
            lines.append(f"### {name}")
            for k in ("capabilities", "weaknesses", "price", "access"):
                if k in info:
                    lines.append(f"- {k}: {info[k]}")
            lines.append("")
    return "\n".join(lines)
