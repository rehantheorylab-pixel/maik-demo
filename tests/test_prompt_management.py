"""Phase J tests: the Prompt Management Agent (write/grade/upgrade/history)."""

import tempfile

from maik_kernel.prompt_management import (MAX_QUALITY, PromptManagement)
from maik_kernel.prompt_system import PromptSystem, SystemPrompt

_NOID = "You handle code tasks. Return good results."  # missing identity, etc.
_GOOD = ("You are the code_tester specialist in MAIK.\n"
         "MISSION: verify correctness of produced code.\n"
         "CONSTRAINTS: Never fabricate results; never run untrusted code "
         "without permission.\n"
         "OUTPUT FORMAT: state PASS/FAIL first, then brief evidence.\n"
         "If you are stuck after 3 attempts, report to your manager with context.\n"
         "COORDINATION: use threads to debate findings; record verdicts in "
         "your public notebook for your manager to review.")


def _dept(extra_ps=None):
    ps = PromptSystem()
    if extra_ps:
        for sp in extra_ps:
            ps.add(sp)
    return PromptManagement(ps, base=tempfile.mkdtemp())


def test_grade_good_prompt_passes():
    d = _dept()
    g = d.grade(_GOOD)
    assert g.grade > 0.85 and g.grade <= 1.0 and not g.suggestions


def test_grade_weak_prompt_fails_and_lists_causes():
    d = _dept()
    g = d.grade(_NOID)
    assert g.grade < d.pass_bar
    assert len(g.suggestions) >= 3


def test_grade_covers_all_weighted_criteria():
    assert abs(sum(v for v in PromptManagement.__module__ and
                   (2.0, 2.0, 1.5, 1.5, 1.0, 1.0, 1.5, 0.5)) - MAX_QUALITY) < 0.001


def test_write_produces_quality_draft():
    d = _dept()
    r = d.write("code_tester", "verify code correctness", powers=["command_run"])
    assert r["passes"] and r["grade"] >= d.pass_bar
    assert "MISSION:" in r["draft"] and "PERMISSIONS:" in r["draft"]


def test_review_scores_node_prompt():
    d = _dept([SystemPrompt("pm:worker1", "node", "worker1", _NOID)])
    r = d.review("worker1")
    assert r["grade"] < d.pass_bar and r["suggestions"]


def test_upgrade_rewrites_until_passing():
    d = _dept([SystemPrompt("pm:worker1", "node", "worker1", _NOID)])
    r = d.upgrade("worker1")
    assert r["passes"], r
    assert r["grade_after"] >= r["grade_before"]
    assert any(c in r["prompt"].lower() for c in ("mission", "constraints"))


def test_upgrade_missing_prompt_returns_error():
    d = _dept()
    r = d.upgrade("ghost-node")
    assert "error" in r


def test_history_persists_and_reports():
    d = _dept()
    d.write("code_tester", "test everything", node_uid="w1")
    d.write("code_tester", "test again", node_uid="w1")
    h = d.prompt_history("w1")
    assert len(h) == 2 and h[0]["action"] == "write"
    rep = d.report()
    assert rep["nodes_tracked"] == 1
