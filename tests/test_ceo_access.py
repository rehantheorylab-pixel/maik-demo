"""Phase L tests: CEO access layer — shell, files, deploy, plugins, MCP."""

import tempfile
from pathlib import Path

from maik_kernel.ceo_access import CeoAccess
from maik_kernel.cli_deployer import CLIDeployer
from maik_kernel.integrations import IntegrationRegistry
from maik_kernel.org_chart import OrgChart, Powers


def _console(org=None, tmpdir=None):
    tmpdir = tmpdir or tempfile.mkdtemp()
    return CeoAccess(workdir=Path(tmpdir), org_chart=org)


def test_status_lists_shell_and_probes():
    c = _console()
    s = c.status()
    assert s["shell"]  # powershell on windows, sh on unix
    assert "deploy_tools" in s and "mcp_servers" in s


def test_shell_dry_run_by_default():
    c = _console()
    r = c.shell("echo phase-l-test")
    assert r["ok"] is True and "DRY RUN" in r["result"]


def test_shell_real_execution_when_allowed():
    c = _console()
    c.runner.allow = True
    r = c.shell("echo hello-maik")
    assert r["ok"] is True and "hello-maik" in r["result"]


def test_path_escape_rejected():
    c = _console()
    r = c.file_create("../../evil.txt", "x")
    assert r["ok"] is False and "escape" in r["error"]


def test_file_create_and_read():
    c = _console()
    # dry-run is the default: reports what would happen without writing
    r = c.file_create("phase_l.txt", "written by the CEO")
    assert r["ok"] is True and "DRY RUN" in r["result"]
    # allow mode writes for real
    c.runner.allow = True
    c2 = _console()
    c2.runner.allow = True
    c2.file_create("phase_l.txt", "written by the CEO")
    assert c2.file_read("phase_l.txt")["ok"] is True


def test_ceo_powers_check_with_org():
    chart = OrgChart.default()
    ceo = chart.ceos()[0]
    ceo.powers = Powers(False, False, False, False, False)
    c = CeoAccess(workdir=Path(tempfile.mkdtemp()), org_chart=chart)
    r = c.shell("echo x")
    assert r["ok"] is False and "command_run" in r["permission"]


def test_deploy_missing_tool_returns_install_hint():
    c = _console()
    r = c.deploy("nonexistent-tool-xyz", "do a task")
    assert r["ok"] is False and "not found" in r["error"]


def test_deploy_available_tool_runs(tmp_path):
    c = CeoAccess(workdir=Path(tmp_path))
    # python3 is always present and CLIDeployer task-flag passes through
    r = c.deploy("python3", "print(2+2)", timeout=20)
    # python3 may or may not be in the deployer registry — probe first
    if c.deployer.probe("python3")["available"]:
        assert r["ok"] is True
    else:
        assert "not found" in r["error"] or r.get("ok") is False


def test_audit_trail_records_actions():
    c = _console()
    c.shell("echo a")
    c.file_create("b.txt", "c")
    a = c.audit()
    assert len(a) >= 2 and a[0]["action"] == "shell"


def test_tool_plugins_lists_builtins():
    c = _console()
    r = c.tool_plugins()
    names = [p["name"] for p in r["plugins"]]
    assert "vscode" in names and "aider" in names


def test_mcp_unknown_server_errors_cleanly():
    c = _console()
    r = c.mcp_connect("ghost-server")
    assert r["ok"] is False
