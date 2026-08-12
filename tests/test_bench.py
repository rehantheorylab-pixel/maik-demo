import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")
os.environ["MAIK_STUB"] = "1"

from maik_kernel.bench_truth import TruthBench, JUDGE_EXACT, JUDGE_CONTAINS
from maik_kernel.learn import LearningSystem


def test_judge_exact():
    bench = TruthBench()
    assert bench._judge(next(p for p in bench.problems if p.id == "m1"), "391")
    assert not bench._judge(next(p for p in bench.problems if p.id == "m1"), "392")


def test_judge_contains_with_alts():
    bench = TruthBench()
    p = next(x for x in bench.problems if x.id == "v1")
    assert bench._judge(p, "No, this is incorrect. 9 x 8 = 72.")
    assert not bench._judge(p, "Yes it is correct")


def test_summary_fields():
    bench = TruthBench()
    s = bench.summary([
        __import__("maik_kernel.bench_truth", fromlist=["BenchRow"]).BenchRow(
            pid="m1", correct=True, tier="flash", pattern="exact_arith",
            cost_usd=0.001, duration_s=0.1, answer="391"),
        __import__("maik_kernel.bench_truth", fromlist=["BenchRow"]).BenchRow(
            pid="m2", correct=False, tier="small", pattern=None,
            cost_usd=0.002, duration_s=0.2, answer="wrong"),
    ])
    assert s["accuracy"] == 0.5 and s["total_cost_usd"] == 0.003
