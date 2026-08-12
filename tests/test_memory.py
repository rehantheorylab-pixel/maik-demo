import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")

from maik_kernel.memory import (L1Memory, L2Memory, L3Memory, ThoughtVDB,
                                MemorySystem, Episode)


def _make_episode(problem="Calculate 2+2", answer="4", correct=True,
                  cost=0.01, tier="flash", conf=0.9):
    return Episode(problem=problem, answer=answer, confidence=conf,
                   correct=correct, cost_usd=cost, tier=tier)


def test_l1_working_memory():
    m = L1Memory()
    m.set("k", "v")
    assert m.get("k") == "v"
    m.clear()
    assert m.get("k") is None


def test_l2_record_and_accuracy():
    with tempfile.TemporaryDirectory() as td:
        l2 = L2Memory(Path(td) / "e.jsonl")
        l2.record(_make_episode(), correct=True)
        l2.record(_make_episode(answer="5"), correct=False)
        assert l2.accuracy() == 0.5
        assert l2.total_cost() == 0.02
        assert len(l2.recent(5)) == 2
        # persistence across objects
        l2b = L2Memory(Path(td) / "e.jsonl")
        assert len(l2b.episodes) == 2


def test_l3_distill():
    with tempfile.TemporaryDirectory() as td:
        l3 = L3Memory(Path(td) / "f.json")
        facts = l3.distill([_make_episode(problem="Calculate 3 x 4")])
        assert len(facts) == 1
        # duplicate signature not re-distilled
        assert not l3.distill([_make_episode(problem="Calculate 3 x 4")])
        # different problem distills again
        assert len(l3.distill([_make_episode(problem="Explain black holes")])) == 1


def test_thought_vdb():
    tv = ThoughtVDB()
    tv.add("the capital of france is paris")
    tv.add("jupiter is the largest planet in the solar system")
    tv.add("photosynthesis converts sunlight to chemical energy")
    top, _ = tv.search("france capital city", 1)[0]
    assert "paris" in top.lower()


def test_memory_system_records():
    with tempfile.TemporaryDirectory() as td:
        ms = MemorySystem(Path(td) / "mem")
        from maik_kernel.executor import ExecutionResult
        from maik_kernel.config import Config, ModelTier
        res = ExecutionResult(run_id="r1", problem="Calculate 2+2", answer="4",
                              confidence=0.9, tier_used=ModelTier.FLASH,
                              cost_usd=0.001, duration_s=0.05, provider="stub",
                              model_used="stub/x", escalations=0, agents_used=1, notes=[],
                              prompt_tokens=10, completion_tokens=4, decision=None)
        ms.record_run(res, correct=True)
        s = ms.status()
        assert s["episodes"] == 1 and s["accuracy"] == 1.0 and s["facts"] == 1
