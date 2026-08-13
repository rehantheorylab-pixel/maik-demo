"""Phase H3-H6 tests: prompt system, dual notebooks, command runner, CLI deployer."""

import tempfile
from pathlib import Path

import pytest

from maik_kernel.org_chart import OrgChart, NodeLevel, Powers
from maik_kernel.prompt_system import (PromptSystem, ROLE_TEMPLATES,
                                       LEVEL_GUIDELINES, PromptError)
from maik_kernel.notebooks import Notebooks, NotebookError
from maik_kernel.command_runner import CommandRunner, CommandError
from maik_kernel.cli_deployer import CLIDeployer, DeployerError


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def org():
    o = OrgChart.light()
    ceo = o.ceos()[0]
    mgr = o.add_manager(ceo.uid, "DevMgr", role="planner", domain="code")
    o.add_agent(mgr.uid, "Writer", role="code_writer", domain="code",
                commands=True, files=True)
    o.add_agent(mgr.uid, "Tester", role="code_tester", domain="code")
    return o


# ---------------- H3: prompt system -----------------------------------
def test_role_templates_present():
    assert "code_writer" in ROLE_TEMPLATES
    assert "code_debugger" in ROLE_TEMPLATES
    assert len(ROLE_TEMPLATES) >= 10


def test_resolve_contains_self_block(org):
    ps = PromptSystem(org)
    w = org.find("Writer")
    text = ps.resolve(w)
    assert "You are Writer" in text
    assert "Role: code_writer" in text
    assert "You report to manager DevMgr" in text
    assert "Your CEO is Chief Code" in text
    assert "command_run" in text
    assert "UTC time:" in text
    assert "blackboard" in text.lower()


def test_resolve_includes_role_template(org):
    ps = PromptSystem(org)
    text = ps.resolve(org.find("Writer"))
    assert "MISSION" in text and "RULES" in text


def test_resolve_unknown_role_still_works(org):
    ps = PromptSystem(org)
    node = org.add_agent(org.find("DevMgr").uid, "Odd", role="zebra_keeper")
    text = ps.resolve(node)
    assert "You are Odd" in text  # self block always present


def test_node_prompt_override(org):
    ps = PromptSystem(org)
    w = org.find("Writer")
    sp = ps.add if False else None
    from maik_kernel.prompt_system import SystemPrompt
    ps.add(SystemPrompt("p1", "node", w.uid, "EXTRA: obey only me"))
    w.prompt_id = "p1"
    text = ps.resolve(w)
    assert "EXTRA: obey only me" in text


def test_update_prompt_requires_editable(org, tmpdir):
    ps = PromptSystem(org)
    from maik_kernel.prompt_system import SystemPrompt
    ps.add(SystemPrompt("locked", "node", "x", "text", editable=False))
    with pytest.raises(PromptError):
        ps.update_text("locked", "new", "user")


def test_guidelines_for_all_levels():
    for lv in ("ceo", "manager", "agent", "subagent"):
        g = PromptSystem.describe_prompt_guidelines(lv)
        assert "must contain" in g or "mission" in g.lower() or "define" in g.lower()
    assert "Unknown role" in PromptSystem.describe_prompt_guidelines("nope")


def test_build_prompt():
    p = PromptSystem.build_prompt("code_tester", mission="break everything",
                                  constraints=["never fix"])
    assert "ROLE: Code Tester" in p
    assert "break everything" in p
    assert "never fix" in p


def test_persistence_roundtrip(org, tmpdir):
    from maik_kernel.prompt_system import SystemPrompt
    ps = PromptSystem(org)
    ps.add(SystemPrompt("saved", "node", "n1", "persist me"))
    ps.save(tmpdir / "p.json")
    ps2 = PromptSystem.load(org, tmpdir / "p.json")
    assert ps2.get("saved").text == "persist me"


# ---------------- H4: notebooks ---------------------------------------
def test_public_notebook_visible_to_all(org, tmpdir):
    nb = Notebooks(org, base=tmpdir)
    w = org.find("Writer")
    nb.write(w.uid, "public", "started coding")
    t = org.find("Tester")
    rows = nb.read(w.uid, "public", viewer_uid=t.uid)
    assert rows and rows[0]["content"] == "started coding"


def test_hidden_notebook_only_chain(org, tmpdir):
    nb = Notebooks(org, base=tmpdir)
    w = org.find("Writer")
    nb.write(w.uid, "hidden", "suspicious result")
    assert nb.read(w.uid, "hidden", viewer_uid=org.ceos()[0].uid)
    with pytest.raises(NotebookError):
        nb.read(w.uid, "hidden", viewer_uid=org.find("Tester").uid)


def test_bad_kind_rejected(org, tmpdir):
    nb = Notebooks(org, base=tmpdir)
    with pytest.raises(NotebookError):
        nb.write(org.find("Writer").uid, "diary", "x")


def test_notebook_summary(org, tmpdir):
    nb = Notebooks(org, base=tmpdir)
    nb.write(org.find("Writer").uid, "public", "a")
    s = nb.summary()
    assert s["nodes_with_notes"] == 1


# ---------------- H5: command runner ----------------------------------
def test_deny_without_power(org, tmpdir):
    cr = CommandRunner(workdir=tmpdir)
    t = org.find("Tester")
    r = cr.execute(t, "shell", "echo hi")
    assert not r["ok"] and "denied" in r["permission"]


def test_dry_run_default(org, tmpdir):
    cr = CommandRunner(workdir=tmpdir)
    r = cr.execute(org.ceos()[0], "shell", "echo live")
    assert r["ok"] and "DRY RUN" in r["result"]


def test_allow_executes(org, tmpdir):
    cr = CommandRunner(workdir=tmpdir, allow=True)
    r = cr.execute(org.ceos()[0], "shell", "echo ok")
    assert r["ok"] and "ok" in r["result"]


def test_file_write(org, tmpdir):
    cr = CommandRunner(workdir=tmpdir, allow=True)
    w = org.find("Writer")
    r = cr.execute(w, "file", "sub/note.txt\nhello world")
    assert r["ok"]
    assert (tmpdir / "sub" / "note.txt").read_text() == "hello world"


def test_path_escape_blocked(org, tmpdir):
    cr = CommandRunner(workdir=tmpdir, allow=True)
    r = cr.execute(org.ceos()[0], "file", "../../evil\nx")
    assert not r["ok"]


def test_automation_hook(org):
    cr = CommandRunner()
    r = cr.execute(org.ceos()[0], "browser", "click icon")
    assert not r["ok"] and "Phase I" in r["permission"]


# ---------------- H6: CLI deployer ------------------------------------
def test_probe_unknown():
    d = CLIDeployer()
    assert not d.probe("no-such-tool")["available"]


def test_registry_list():
    d = CLIDeployer()
    assert "aider" in d.tools()


def test_spawn_missing_tool():
    d = CLIDeployer()
    with pytest.raises(DeployerError):
        d.spawn("no-such-tool", "task")


def test_spawn_real_echo_tool(tmpdir):
    # register /bin/echo as a fake worker tool
    d = CLIDeployer()
    d.register("echo-tool", ["/bin/echo"], "--")
    r = d.spawn("echo-tool", "hello worker")
    assert r["ok"] and "hello worker" in r["output"]
    assert len(d.history()) == 1


def test_spawn_timeout(tmpdir):
    d = CLIDeployer(timeout_s=2)
    d.register("sleepy", ["/bin/sleep"], "")
    r = d.spawn("sleepy", "10", timeout=1)  # valid interval, exceeds timeout
    assert not r["ok"] and "timed out" in r["output"]
