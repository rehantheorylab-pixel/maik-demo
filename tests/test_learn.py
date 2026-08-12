import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")
from maik_kernel.learn import LearningSystem, K_ELO


def test_elo_moves():
    td = Path(tempfile.mkdtemp()) / "learn"
    ls = LearningSystem(td)
    ls.judge("math", "math_solver", won=True)
    win_rating = ls.elo["domain:math"].rating
    ls2 = LearningSystem(td)  # reload from persistence
    ls2.judge("math", "math_solver", won=False)
    loss_rating = ls2.elo["domain:math"].rating
    assert win_rating > 1200
    assert loss_rating < win_rating


def test_rankings_order():
    ls = LearningSystem(Path(tempfile.mkdtemp()) / "learn")
    for _ in range(10):
        ls.judge("math", "math_solver", won=True)
    for _ in range(3):
        ls.judge("creative", "brainstormer", won=True)
    r = ls.rankings()
    assert r["domain:math"] > r["domain:creative"]


def test_postmortem_persist():
    ls = LearningSystem(Path(tempfile.mkdtemp()) / "learn")
    ls.postmortem("Calculate 1/0", "infinity", "error", 0.9, "flash")
    ls2 = LearningSystem(ls.base)
    assert len(ls2.postmortems) == 1


def test_contradiction_mined_when_divergent():
    ls = LearningSystem(Path(tempfile.mkdtemp()) / "learn")
    rec = ls.mine_contradiction(
        "Capital of Australia",
        ["Sydney", "Canberra is the capital of Australia"],
        ["gemini-flash", "gpt-4o-mini"])
    assert rec is not None
    # similar answers are not contradictions
    rec2 = ls.mine_contradiction("2+2", ["4", "four (4)"], ["a", "b"])
    assert rec2 is None


def test_contradiction_persist():
    ls = LearningSystem(Path(tempfile.mkdtemp()) / "learn")
    ls.mine_contradiction("p", ["a", "b c d e f g"], ["m1", "m2"])
    ls2 = LearningSystem(ls.base)
    assert len(ls2.contradictions) == 1
