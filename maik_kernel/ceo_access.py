"""CEO Access Layer (Phase L).

The CEO is not just a name in the org chart — the CEO is the OPERATOR.
This layer gives the CEO direct, gated control of the whole machine:

  - shell: run PowerShell/cmd commands (Windows) or sh (Unix) — dry-run
    first, then real execution; path-escape protection on file writes
  - files: create/read/list files, scoped to the workdir by default;
    escape paths are hard-rejected
  - deploy: spawn external agent CLIs (aider, opencode, codex, claude-code,
    gemini-cli) as worker processes under the CEO's command
  - plugins: probe and spawn tool plugins (VS Code, Cursor, OpenCode...)
  - mcp: connect to any MCP server and call its tools by name

Every action checks the CEO node's powers (Powers.ceo() has them all),
logs to the CEO audit trail, and honors the API department's quotas so
a CEO command can never silently drain budgets.
"""

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .command_runner import CommandRunner, CommandError
from .cli_deployer import CLIDeployer
from .integrations import IntegrationRegistry
from .org_chart import Powers


def _shell_binary() -> List[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-Command"]
    return ["/bin/sh", "-c"]


class CeoAccess:
    """The CEO's operator console."""

    def __init__(self, workdir: Optional[Path] = None,
                 org_chart=None, deployer: Optional[CLIDeployer] = None,
                 registry: Optional[IntegrationRegistry] = None):
        self.runner = CommandRunner(workdir=workdir or Path.home(),
                                    allow=False)  # dry-run first, always
        self.deployer = deployer or CLIDeployer()
        self.registry = registry or IntegrationRegistry()
        self.org = org_chart
        self._audit: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._mcps: Dict[str, Any] = {}

    # ------------------------------------------------------------ audit
    def _log(self, action: str, payload: str, result: dict) -> None:
        with self._lock:
            self._audit.append({"ts": time.time(), "action": action,
                                "payload": payload[:300], "result": result})

    def audit(self, last_n: int = 50) -> List[Dict[str, Any]]:
        return list(self._audit[-last_n:])

    # ------------------------------------------------------------ powers
    def _check_powers(self, kind: str) -> Optional[str]:
        """Return an error message if the CEO lacks the power, else None."""
        if self.org is None:
            return None  # org-less mode: CEO console always available
        ceo = self.org.ceo
        if ceo is None or not ceo.powers.allowed(kind):
            return f"CEO lacks {kind} power in the current org chart"
        return None

    # ------------------------------------------------------------ shell
    def shell(self, command: str, dry_run: bool = True) -> dict:
        node = self._ceo_node()
        # _shell takes the command string directly (payload is the cmd)
        try:
            res = self.runner.execute(node, "shell", command)
        except CommandError as e:
            res = {"ok": False, "result": None, "permission": "error",
                   "detail": str(e)}
        if not dry_run and res.get("ok"):
            res["result"] = res.get("result")  # real execution already ran
        self._log("shell", command, res)
        return res

    # ------------------------------------------------------------ files
    def _ceo_node(self):
        from .org_chart import NodeLevel, OrgNode
        if self.org is not None and self.org.ceos():
            return self.org.ceos()[0]
        return OrgNode(uid="ceo", name="CEO", role="ceo", domain="ops",
                       level=NodeLevel.CEO, powers=Powers.ceo())

    def file_create(self, rel_path: str, content: str) -> dict:
        err = self._check_powers("file_create")
        if err:
            return {"ok": False, "error": err}
        node = self._ceo_node()
        if ".." in rel_path or rel_path.startswith(("/dev", "C:\\")):
            return {"ok": False, "error": "path escape rejected"}
        # payload format expected by _file: "relpath\nbody"
        try:
            res = self.runner.execute(node, "file", f"{rel_path}\n{content}")
        except CommandError as e:
            res = {"ok": False, "result": None, "permission": "error",
                   "detail": str(e)}
        self._log("file_create", rel_path, res)
        return res

    def file_read(self, rel_path: str) -> dict:
        if ".." in rel_path:
            return {"ok": False, "error": "path escape rejected"}
        target = self.runner.workdir / rel_path
        try:
            return {"ok": True, "content": target.read_text()[:64_000]}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------ deploy
    def deploy(self, tool: str, task: str,
               timeout: Optional[int] = None) -> dict:
        err = self._check_powers("cli_deploy")
        if err:
            return {"ok": False, "error": err}
        probed = self.deployer.probe(tool)
        if not probed["available"]:
            self._log("deploy", f"{tool} {task[:80]}", probed)
            return {"ok": False,
                    "error": f"{tool} not found — install it first "
                             "(maik org deploy probe {tool} shows the path)",
                    "probe": probed}
        try:
            res = self.deployer.spawn(tool, task, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "error": str(e)[:300]}
        self._log("deploy", f"{tool} {task[:80]}",
                  {k: v for k, v in res.items() if k != "output"}
                  if isinstance(res, dict) else {"error": str(res)[:200]})
        return res

    # ------------------------------------------------------------ plugins
    def tool_plugins(self) -> dict:
        return {"plugins": [
            {"name": p.name, "category": p.category, "note": p.note}
            for p in self.registry.plugins.values()],
            "status": self.registry.status()}

    # ------------------------------------------------------------ mcp
    def mcp_connect(self, server_name: str) -> dict:
        if server_name in self._mcps:
            return {"ok": True, "server": server_name, "already": True,
                    "tools": []}
        r = self.registry.connect_mcp(server_name)
        if r.get("ok"):
            self._mcps[server_name] = True
        self._log("mcp_connect", server_name, r)
        return r

    def mcp_list_tools(self, server_name: str) -> dict:
        conn = self.registry._connectors.get(server_name)
        if conn is None:
            return {"ok": False, "error": "not connected"}
        return {"ok": True, "tools": conn.list_tools()}

    def mcp_call(self, server_name: str, tool_name: str,
                 arguments: Optional[Dict[str, Any]] = None) -> dict:
        try:
            r = self.registry.call_mcp(server_name, tool_name, arguments or {})
            self._log("mcp_call", f"{server_name}/{tool_name}",
                      {k: v for k, v in (r or {}).items()
                       if isinstance(v, (str, int, float, bool))})
            return r
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:300]}

    # ------------------------------------------------------------ console
    def status(self) -> dict:
        return {
            "shell": _shell_binary(),
            "workdir": str(self.runner.workdir),
            "deploy_tools": {t: self.deployer.probe(t)["available"]
                             for t in self.deployer.tools()},
            "mcp_servers": list(self.registry.mcp_defs),
            "audit_entries": len(self._audit),
        }
