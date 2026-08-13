"""Phase M tests: PC & browser automation operator — mouse/keyboard,
screen capture, browser driving, scoped file ops, audit logging."""

import tempfile
from pathlib import Path

from maik_kernel.automation import (AutomationAgent, AutomationError,
                                    AutomationPolicy, AutomationScope,
                                    FileOperator, InputOperator,
                                    ScreenReader)
from maik_kernel.org_chart import OrgNode, NodeLevel, Powers


def _policy(scope=AutomationScope.PROJECT, powers=None, dry_run=True):
    node = OrgNode(uid="a1", name="AutomationWorker", role="worker",
                   domain="ops", level=NodeLevel.AGENT,
                   powers=powers or Powers(False, False, True, True, False))
    return AutomationPolicy(node=node, scope=scope,
                            workdir=Path(tempfile.mkdtemp()),
                            dry_run=dry_run)


def _agent(scope=AutomationScope.PROJECT, powers=None, dry_run=True):
    return AutomationAgent(_policy(scope, powers, dry_run))


# -- powers gating --------------------------------------------------------

def test_no_screen_power_blocks_capture():
    a = _agent(powers=Powers(False, False, False, True, False))
    assert a.capture()["ok"] is False and "screen_read" in a.capture()["error"]


def test_no_browser_power_blocks_goto():
    a = _agent(powers=Powers(False, False, True, False, False))
    assert a.goto(url="https://example.com")["ok"] is False


def test_no_keymouse_power_blocks_move():
    a = _agent(powers=Powers(False, False, True, False, False))
    # worker without browser_automation and non-computer scope
    assert a.move_mouse(x=500, y=400)["ok"] is False


# -- dry-run defaults -----------------------------------------------------

def test_move_dry_run_reports_plan():
    a = _agent(dry_run=True)
    r = a.move_mouse(x=500, y=400)
    assert r["ok"] is True and "DRY RUN" in r["result"]


def test_click_dry_run():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.click(x=100, y=200)["result"]


def test_drag_dry_run():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.drag(x1=10, y1=10, x2=100, y2=100)["result"]


def test_type_dry_run():
    a = _agent(dry_run=True)
    r = a.type_text(text="hello maik")
    assert r["ok"] is True and "DRY RUN" in r["result"]


def test_press_dry_run():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.press(keys="ctrl+c")["result"]


def test_browser_goto_dry_run_and_url_validation():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.goto(url="https://example.com")["result"]
    assert a.goto(url="not-a-url")["ok"] is False


def test_browser_click_fill_dry_run():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.click_selector(selector="#go")["result"]
    assert "DRY RUN" in a.fill(selector="#q", value="maik")["result"]


# -- out-of-bounds --------------------------------------------------------

def test_move_out_of_screen_rejected():
    a = _agent()
    r = a.move_mouse(x=-5, y=-5)
    assert r["ok"] is False and "outside" in r["error"]


# -- scoped file ops ------------------------------------------------------

def test_file_write_dry_run():
    a = _agent(dry_run=True)
    r = a.file_write(rel="out.txt", content="phase m")
    assert r["ok"] is True and "DRY RUN" in r["result"]


def test_file_write_real_respects_scope():
    a = _agent(dry_run=False)
    r = a.file_write(rel="out.txt", content="phase m")
    assert r["ok"] is True and (a.files.policy.workdir / "out.txt").exists()


def test_file_ops_outside_project_rejected():
    a = _agent(dry_run=False)
    r = a.file_write(rel="../escape.txt", content="x")
    assert r["ok"] is False and "outside" in r["error"]


def test_one_file_scope_allows_only_base():
    a = _agent(scope=AutomationScope.ONE_FILE, dry_run=False)
    r = a.file_write(rel="sub/file.txt", content="x")
    assert r["ok"] is False


def test_file_read_list_copy_delete():
    a = _agent(dry_run=False)
    a.file_write(rel="f1.txt", content="hello")
    assert a.file_read(rel="f1.txt")["content"] == "hello"
    r = a.file_list()
    assert any(e["name"] == "f1.txt" for e in r["entries"])
    assert a.file_copy(src="f1.txt", dst="f2.txt")["ok"] is True
    assert a.file_delete(rel="f1.txt")["ok"] is True
    assert a.file_delete(rel="f1.txt")["ok"] is False  # gone


def test_move_copy_dry_run():
    a = _agent(dry_run=True)
    assert "DRY RUN" in a.file_move(src="a.txt", dst="b.txt")["result"]
    assert "DRY RUN" in a.file_copy(src="a.txt", dst="b.txt")["result"]


# -- automation agent act dispatch ----------------------------------------

def test_act_dispatch_unknown_action():
    a = _agent()
    r = a.act("fly_to_mars", {})
    assert r["ok"] is False and "unknown" in r["error"]


def test_act_audit_trail():
    a = _agent()
    a.act("move_mouse", {"x": 1, "y": 1})
    a.act("click", {"x": 1, "y": 1})
    assert len(a.audit()) == 2


def test_browser_available_reports_backend():
    a = _agent()
    av = a.browser.available()
    assert "playwright" in av and "browser_power" in av
