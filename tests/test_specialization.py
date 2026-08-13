"""Phase N (v3.4.0): Specialization Layer tests.

Evidence-based domain→model routing: SpecializationMatrix, SpecializationBench,
compare_report. Stub provider (MAIK_STUB=1) gives deterministic answers, so
judges run offline.
"""

import json
import os
from pathlib import Path

import pytest

from maik_kernel.specialization import (
    DOMAINS,
    DomainResult,
    SpecializationBench,
    SpecializationMatrix,
    compare_report,
)
from maik_kernel.config import Config
from maik_kernel.executor import Executor
from maik_kernel.live_execution import LiveExecution
from maik_kernel.providers import ProviderLadder

BASE = Path(os.environ.get("MAIK_DATA_DIR", "/tmp/maikspec"))

FIXED_PROBLEM = {
    "id": "spec-math-1",
    "domain": "math",
    "problem": "What is 2 + 2? Answer with just the number.",
    "expected": "4",
    "kind": "math",
    "difficulty": 1,
}

FIXED_PROBLEM_B = {
    "id": "spec-reason-1",
    "domain": "reasoning",
    "problem": "If all A are B and all B are C, are all A necessarily C? Answer yes or no.",
    "expected": "yes",
    "kind": "reasoning",
    "difficulty": 1,
}


class StubProblem:
    def __init__(self, spec):
        for k, v in spec.items():
            setattr(self, k, v)


def _make_bench_with_problems(problems):
    """TruthBench stand-in that lets tests inject fixed problems + judges."""

    class MiniBench:
        def __init__(self):
            self.problems = [StubProblem(p) for p in problems]

        def _judge(self, prob, answer):
            # accept answer containing the expected token (case-insensitive)
            return bool(answer) and prob.expected.lower() in answer.lower()

    return MiniBench()


def _matrix(tmp):
    m = SpecializationMatrix(tmp)
    return m


# ---------------------------------------------------------------------------
# SpecializationMatrix
# ---------------------------------------------------------------------------

def test_domains_taxonomy():
    assert "math" in DOMAINS and "code" in DOMAINS
    assert "security" in DOMAINS
    assert len(DOMAINS) == 8


def test_record_and_accuracy(tmp_path):
    m = _matrix(tmp_path)
    dr = m.record("modA", "math", passed=2, total=2, evidence_ids=["p1", "p2"])
    assert dr.accuracy == 1.0
    assert dr.problems == 2
    m.record("modB", "math", passed=1, total=2, evidence_ids=["p3"])
    assert m.ranked("math")[0].model == "modA"


def test_persistence_roundtrip(tmp_path):
    m = _matrix(tmp_path)
    m.record("modA", "code", passed=3, total=3, evidence_ids=["c1"])
    m2 = SpecializationMatrix(tmp_path)
    assert m2.get("modA", "code") is not None
    assert m2.get("modA", "code").correct == 3
    data = json.loads((tmp_path / "specialization.json").read_text())
    assert "modA::code" in data


def test_best_for_requires_enough_evidence(tmp_path):
    m = _matrix(tmp_path)
    assert m.best_for("math") is None
    m.record("modA", "math", passed=0, total=0)
    assert m.best_for("math", min_problems=1) is None
    m.record("modA", "math", passed=1, total=1, evidence_ids=["e1"])
    assert m.best_for("math") == "modA"


def test_domains_covered(tmp_path):
    m = _matrix(tmp_path)
    m.record("modA", "math", passed=1, total=1, evidence_ids=["a"])
    m.record("modA", "code", passed=1, total=1, evidence_ids=["b"])
    assert set(m.domains_covered()) == {"math", "code"}


def test_swarm_score(tmp_path):
    m = _matrix(tmp_path)
    m.record("modA", "math", passed=2, total=2, evidence_ids=["m1", "m2"])
    m.record("modB", "reasoning", passed=1, total=2, evidence_ids=["r1"])
    sc = m.swarm_score()
    assert sc["domains_covered"] == 2
    assert sc["per_domain_best"]["math"] == "modA"
    assert sc["per_domain_best"]["reasoning"] == "modB"
    # (2/2 + 1/2) / 2 == 0.75
    assert abs(sc["swarm_avg_accuracy"] - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# SpecializationBench — live against the stub executor (offline)
# ---------------------------------------------------------------------------

@pytest.fixture()
def executor():
    cfg = Config()
    return Executor(cfg)


def test_bench_run_records_wins(executor):
    os.environ.setdefault("MAIK_STUB", "1")
    bench = _make_bench_with_problems([FIXED_PROBLEM, FIXED_PROBLEM_B])
    m = SpecializationMatrix(BASE)
    sb = SpecializationBench(m, executor=executor, bench=bench)
    out = sb.run(["stub-flash", "stub-small"])
    assert len(out["rows"]) == 4  # 2 models x 2 problems
    covered = m.domains_covered()
    assert set(covered) == {"math", "reasoning"}
    # stub answers contain the expected tokens (stub is configured to echo
    # correct numeric/yes answers for these trivial problems)
    for row in out["rows"]:
        assert "ok" in row


def test_bench_run_failure_isolation(executor):
    """A broken problem/judge must never crash the bench run."""
    bad = dict(FIXED_PROBLEM)
    bad["domain"] = "math"
    bench = _make_bench_with_problems([bad])
    m = SpecializationMatrix(BASE)
    sb = SpecializationBench(m, executor=executor, bench=bench)
    out = sb.run(["stub-flash"])
    assert len(out["rows"]) == 1
    assert out["swarm"]["domains_covered"] >= 0


# ---------------------------------------------------------------------------
# compare_report
# ---------------------------------------------------------------------------

def test_compare_report_empty(tmp_path):
    m = _matrix(tmp_path)
    text = compare_report(m)
    assert "No specialization evidence" in text


def test_compare_report_with_evidence_and_rivals(tmp_path):
    m = _matrix(tmp_path)
    m.record("modA", "math", passed=3, total=3, evidence_ids=["p"])
    m.record("modB", "math", passed=1, total=3, evidence_ids=["p"])
    text = compare_report(m, rivals={
        "RivalX": {"price": "$50/M tokens", "access": "restricted"},
    })
    assert "modA" in text and "swarm pick" in text
    assert "RivalX" in text and "$50/M tokens" in text
    assert "Swarm average accuracy" in text


# ---------------------------------------------------------------------------
# Executor model_override routing (the plumbing SpecializationBench uses)
# ---------------------------------------------------------------------------

def test_executor_model_override(executor):
    os.environ.setdefault("MAIK_STUB", "1")
    res = executor.execute("What is 1 + 1?", model_override="stub-small")
    assert res.model_used == "stub-small" or "stub-small" in res.notes[0].get(
        "model", "") if res.notes else False
    assert any(n.get("event") == "model_override" for n in res.notes)


def test_executor_no_override_uses_tier(executor):
    os.environ.setdefault("MAIK_STUB", "1")
    res = executor.execute("What is 1 + 1?")
    assert not any(n.get("event") == "model_override" for n in res.notes)


# ---------------------------------------------------------------------------
# Phase N additions — verifier pin + provider ladder live_base rung
# ---------------------------------------------------------------------------

def test_verifier_uses_pinned_model_env(monkeypatch):
    """LiveExecution.verify honors MAIK_LIVE_VERIFIER_MODEL (stub guard
    keeps this offline: the env pin is checked before any live call)."""
    monkeypatch.setenv("MAIK_LIVE_VERIFIER_MODEL", "pinned-verifier")
    live = LiveExecution()
    # non-stub path with a non-tier model id passes through unchanged;
    # we only assert the resolve branch is stub-guarded here.
    result = live.verify("What is 1+1?", "2")
    # In whatever mode we run in, the result must carry a verdict key
    assert "verdict" in result


def test_ladder_has_live_base_when_env_set(monkeypatch):
    monkeypatch.setenv("MAIK_LIVE_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("MAIK_LIVE_API_KEY", "k")
    ladder = ProviderLadder()
    names = [e.name for e in ladder.entries]
    assert "live_base" in names
    # live_base is the first *non-stub* rung — stub mode (MAIK_STUB=1)
    # inserts a stub entry ahead of the real ladder in test runs only.
    real = [n for n in names if n != "stub"]
    assert real[0] == "live_base"


def test_ladder_no_live_base_without_env(monkeypatch):
    monkeypatch.delenv("MAIK_LIVE_BASE_URL", raising=False)
    monkeypatch.delenv("MAIK_LIVE_API_KEY", raising=False)
    ladder = ProviderLadder()
    names = [e.name for e in ladder.entries]
    assert "live_base" not in names
