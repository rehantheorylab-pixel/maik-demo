"""Permission-gated command execution (Phase H5).

Every runnable action is gated by the node's Powers:
- `shell`    -> powers.command_run
- `file`     -> powers.file_create   (write text to a file)
- `screen`   -> powers.screen_read   -> Phase I automation operator (hook)
- `browser`  -> powers.browser_automation -> Phase I automation operator (hook)

Default policy: CEO and manager have shell+file; agents get powers only when
their manager explicitly granted them. Real shell execution is enabled by
`allow=True` — the default is DRY RUN so nothing executes silently.
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from .org_chart import OrgNode


class CommandError(RuntimeError):
    pass


class CommandRunner:
    def __init__(self, workdir: Optional[Path] = None, allow: bool = False,
                 timeout_s: int = 60):
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.allow = allow
        self.timeout_s = timeout_s

    def execute(self, node: OrgNode, kind: str, payload: str,
                **kw) -> dict:
        """Run a permission-gated action. Returns {ok, result, permission}."""
        power = {"shell": "command_run", "file": "file_create",
                 "screen": "screen_read", "browser": "browser_automation"}
        if not node.powers.allowed(power.get(kind, kind)):
            return {"ok": False, "result": None,
                    "permission": f"denied: {power.get(kind, kind)} not in powers",
                    "detail": ("Ask your manager to deploy a node with "
                               f"{kind} permission, or request a power grant.")}
        try:
            if kind == "shell":
                return self._shell(node, payload, **kw)
            if kind == "file":
                return self._file(node, payload, **kw)
            if kind in ("screen", "browser"):
                return self._automation_hook(node, kind, payload, **kw)
            return {"ok": False, "result": None, "permission": f"unknown kind {kind}"}
        except CommandError as e:
            return {"ok": False, "result": None, "permission": "error",
                    "detail": str(e)}

    # -- kinds ---------------------------------------------------------
    def _shell(self, node: OrgNode, cmd: str, **kw) -> dict:
        if not self.allow:
            return {"ok": True, "result": f"DRY RUN: would execute: {cmd[:200]}",
                    "permission": "allowed (dry-run mode)"}
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(self.workdir), timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            raise CommandError(f"command timed out after {self.timeout_s}s")
        return {"ok": proc.returncode == 0,
                "result": proc.stdout[:4000] or proc.stderr[:4000],
                "permission": "allowed"}

    def _file(self, node: OrgNode, payload: str, **kw) -> dict:
        # payload format: "path/to/file\n<body>"
        if "\n" not in payload:
            raise CommandError("file payload must be 'path\\nbody'")
        rel, body = payload.split("\n", 1)
        dest = (self.workdir / rel).resolve()
        # sandbox: never escape the workdir
        if not str(dest).startswith(str(self.workdir.resolve())):
            raise CommandError(f"refusing path outside workdir: {rel}")
        if not self.allow:
            return {"ok": True, "result": f"DRY RUN: would write {len(body)} bytes to {rel}",
                    "permission": "allowed (dry-run mode)"}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body)
        return {"ok": True, "result": f"wrote {len(body)} bytes to {rel}",
                "permission": "allowed"}

    @staticmethod
    def _automation_hook(node: OrgNode, kind: str, payload: str, **kw) -> dict:
        return {"ok": False, "result": None,
                "permission": "requires automation operator (Phase I)",
                "detail": (f"{kind} automation is not built into the kernel. "
                           "Phase I integrates a best-in-class computer-use "
                           "operator (pixel-perfect mouse/keyboard/screen). "
                           "Until then, request this via a Phase I worker.")}


def system_check(kind: str = "shell") -> dict:
    """Best-effort environment check for a command kind."""
    if kind == "shell":
        sh = shutil.which("sh") or shutil.which("cmd")
        return {"available": bool(sh), "binary": sh}
    return {"available": False, "detail": f"check for kind {kind} unavailable"}
