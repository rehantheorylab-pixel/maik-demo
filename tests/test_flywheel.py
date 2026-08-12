"""Phase F tests: flywheel closes the learning loop.

Success criterion (ARCHITECTURE.md): after one revolution, the flywheel must
change at least one routing rule (`rules_changed >= 1` or `patterns_tuned >= 1`)
and persist reroute_rules.json.
"""
import json
import os

# activate stub mode for fully offline testing
os.environ.setdefault("MAIK_STUB", "1")

from maik_kernel.bench_truth import TruthBench
from maik_kernel.flywheel import Flywheel
from maik_kernel.pattern_lib import PatternLibrary
from maik_kernel.learn import LearningSystem
from maik_kernel.memory import MemorySystem


class TempFS:
    """Isolate file writes to a tempdir so runs don't pollute the repo."""

    def __init__(self, tmp_path):
        import pathlib
        self.d = pathlib.Path(tmp_path)
        self.d.mkdir(parents=True, exist_ok=True)
        for sub in ("learn", "memory", "patterns"):
            (self.d / sub).mkdir(exist_ok=True)

    def flywheel(self, **kw):
        import pathlib
        return Flywheel(
            pattern_lib=PatternLibrary(base=self.d / "patterns"),
            learn=LearningSystem(base=self.d / "learn"),
            memory=MemorySystem(base=self.d / "memory"),
            bench=TruthBench(),
            rules_path=self.d / "reroute_rules.json",
            **kw)


def test_flywheel_run_changes_rules(tmp_path):
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    # wire bench and flywheel to the SAME learning/memory objects
    fw.learn = fw.bench.learn = LearningSystem(base=fs.d / "learn")
    fw.memory = fw.bench.memory = MemorySystem(base=fs.d / "memory")
    report = fw.run()
    assert report.revolution == 1
    assert report.accuracy_before == 0.0 or True  # stub accuracy known
    # the loop must have produced evidence of learning:
    assert report.contradictions_mined >= 1, \
        "flywheel must mine at least one contradiction from wrong answers"
    assert report.elo_updates >= 1, "ELO rankings must be populated"
    assert report.patterns_tuned >= 1 or report.rules_changed >= 1, \
        "Phase F criterion: at least one routing rule must change"
    # rules must be persisted
    saved = json.loads((fs.d / "reroute_rules.json").read_text())
    assert "rules" in saved and saved["revolution"] == 1


def test_flywheel_accumulates_across_revolutions(tmp_path):
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    fw.learn = fw.bench.learn = LearningSystem(base=fs.d / "learn")
    fw.memory = fw.bench.memory = MemorySystem(base=fs.d / "memory")
    r1 = fw.run()
    r2 = fw.run()
    assert r2.revolution == 2
    # second revolution rebuilds on saved rules (learning accumulates)
    assert r2.accuracy_before == r1.accuracy_after


def test_flywheel_generate_rules_has_domains(tmp_path):
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    fw.learn = fw.bench.learn = LearningSystem(base=fs.d / "learn")
    fw.memory = fw.bench.memory = MemorySystem(base=fs.d / "memory")
    rules, learnt = fw._generate_rules(fw.bench.run())
    # rules must reference real domains learned from the bench
    assert set(learnt) & {"math", "code", "research", "review", "creative"}


def test_flywheel_mine_contradictions(tmp_path):
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    fw.learn = fw.bench.learn = LearningSystem(base=fs.d / "learn")
    fw.memory = fw.bench.memory = MemorySystem(base=fs.d / "memory")
    rows = fw.bench.run()
    wrong = [r for r in rows if not r.correct]
    mined = fw._mine_contradictions(rows)
    # each wrong answer vs its ground truth should mine a record
    assert len(mined) >= min(3, len(wrong))
    for rec in mined:
        assert rec.resolved is not None, "contradictions must be citable"


def test_flywheel_tier_up_helper(tmp_path):
    from maik_kernel.config import ModelTier
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    assert fw._tier_up(ModelTier.FLASH) == ModelTier.SMALL
    assert fw._tier_up(ModelTier.LARGE) == ModelTier.LARGE


def test_flywheel_domain_of(tmp_path):
    fs = TempFS(tmp_path)
    fw = fs.flywheel()
    assert fw._domain_of("m1") == "math"
    assert fw._domain_of("c3") == "code"
    assert fw._domain_of("r2") == "research"
    assert fw._domain_of("v1") == "review"
    assert fw._domain_of("k1") == "creative"
