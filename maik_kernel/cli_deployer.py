"""External CLI deployment (Phase H6).

A CEO (or a node with powers.cli_deploy) can spawn a worker from an external
agent CLI — gemini-cli, claude-code, aider, opencode, codex, or any registered
tool found on PATH. The CLI runs as a child process with a task prompt, and
its output is captured with a timeout.

Usage:
    deployer = CLIDeployer()
    deployer.probe("aider")            # is it installed?
    deployer.spawn("aider", "task...", timeout=300)
"""

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    commands: List[str]          # candidate binary names on PATH
    task_flag: str               # how to pass the task: e.g. "prompt"
    note: str


DEFAULT_REGISTRY: Dict[str, ToolSpec] = {
    "gemini-cli": ToolSpec("gemini-cli", ["gemini", "gemini-cli"],
                           "--prompt", "Google Gemini CLI worker"),
    "claude-code": ToolSpec("claude-code", ["claude"], "--print",
                            "Anthropic Claude Code worker"),
    "aider": ToolSpec("aider", ["aider"], "--message",
                      "aider pair-programming worker"),
    "opencode": ToolSpec("opencode", ["opencode"], "--prompt",
                         "opencode worker"),
    "codex": ToolSpec("codex", ["codex"], "--prompt",
                      "OpenAI Codex CLI worker"),
    "openai-agents": ToolSpec("openai-agents", ["agents"], "--message",
                              "OpenAI Agents SDK CLI"),
}


class DeployerError(RuntimeError):
    pass


class CLIDeployer:
    def __init__(self, registry: Optional[Dict[str, ToolSpec]] = None,
                 timeout_s: int = 300):
        self.registry = dict(registry or DEFAULT_REGISTRY)
        self.timeout_s = timeout_s
        self._lock = threading.RLock()
        self._runs: List[dict] = []

    def tools(self) -> List[str]:
        return sorted(self.registry)

    def probe(self, tool: str) -> dict:
        """Check whether a tool is installed on PATH."""
        spec = self.registry.get(tool)
        if spec is None:
            return {"available": False, "error": f"unknown tool {tool}"}
        for cmd in spec.commands:
            if shutil.which(cmd):
                return {"available": True, "binary": cmd, "note": spec.note}
        return {"available": False,
                "detail": f"not on PATH (tried {spec.commands}); install it first"}

    def register(self, name: str, commands: List[str], task_flag: str,
                 note: str = "") -> ToolSpec:
        spec = ToolSpec(name, commands, task_flag, note)
        with self._lock:
            self.registry[name] = spec
        return spec

    def spawn(self, tool: str, task: str, timeout: Optional[int] = None,
              extra_args: Optional[List[str]] = None) -> dict:
        """Spawn an external CLI worker with a task prompt."""
        spec = self.registry.get(tool)
        if spec is None:
            raise DeployerError(f"unknown tool {tool}")
        binary = None
        for cmd in spec.commands:
            if shutil.which(cmd):
                binary = cmd
                break
        if binary is None:
            raise DeployerError(
                f"{tool} not installed (tried {spec.commands})")
        argv = [binary] + (extra_args or [])
        if spec.task_flag:
            argv.append(spec.task_flag)
        argv.append(task)
        t0 = time.time()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout or self.timeout_s)
            out = proc.stdout[:10000] or proc.stderr[:10000]
            run = {"tool": tool, "binary": binary, "task": task[:200],
                   "ok": proc.returncode == 0, "exit_code": proc.returncode,
                   "output": out, "duration_s": round(time.time() - t0, 2)}
        except subprocess.TimeoutExpired:
            run = {"tool": tool, "binary": binary, "task": task[:200],
                   "ok": False, "exit_code": -1,
                   "output": f"timed out after {timeout or self.timeout_s}s",
                   "duration_s": timeout or self.timeout_s}
        with self._lock:
            self._runs.append(run)
        return run

    def history(self) -> List[dict]:
        with self._lock:
            return list(self._runs)

    def summary(self) -> dict:
        return {
            "tools": {t: self.probe(t)["available"] for t in self.tools()},
            "runs": len(self._runs),
            "last": self._runs[-1] if self._runs else None,
        }
