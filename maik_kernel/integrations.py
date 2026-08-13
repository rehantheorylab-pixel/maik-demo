"""Tool & MCP integration registry (Phase H9).

Two layers:
1. TOOL PLUGINS — external IDE/agent tools a CEO can activate as workers
   (VS Code cli, Cursor, OpenCode, aider, gemini-cli, claude-code, codex...).
   This is the deployment layer the CLI deployer uses.
2. MCP CONNECTORS — Model Context Protocol servers. MCP is the standard way
   modern AI tools expose capabilities (files, browser, shell, databases...)
   to an AI. MAIK can register any MCP server by name + command; when a
   worker needs a capability the connector forwards JSON-RPC tool calls.

Both layers are registries first: discovering/activating a real install
happens on the user's machine (the kernel stays portable).
"""

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ToolPlugin:
    name: str
    commands: List[str]        # candidate binaries
    cli_args: str              # default task-passing mode
    category: str              # ide | agent-cli | automation | other
    note: str = ""


DEFAULT_TOOL_PLUGINS: List[ToolPlugin] = [
    ToolPlugin("vscode", ["code", "code.cmd"], "code --wait", "ide",
               "Visual Studio Code CLI"),
    ToolPlugin("cursor", ["cursor", "cursor.exe"], "cursor --file", "ide",
               "Cursor editor CLI"),
    ToolPlugin("opencode", ["opencode"], "opencode --prompt", "agent-cli",
               "opencode terminal agent"),
    ToolPlugin("claude-code", ["claude"], "claude --print", "agent-cli",
               "Anthropic Claude Code"),
    ToolPlugin("gemini-cli", ["gemini", "gemini-cli"], "gemini --prompt",
               "agent-cli", "Google Gemini CLI"),
    ToolPlugin("aider", ["aider"], "aider --message", "agent-cli",
               "aider pair programmer"),
    ToolPlugin("codex", ["codex"], "codex --prompt", "agent-cli",
               "OpenAI Codex CLI"),
]


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPConnector:
    """Stdio transport to one MCP server (JSON-RPC 2.0)."""

    def __init__(self, name: str, command: str, args: Optional[List[str]] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self._proc = None
        self._lock = threading.RLock()
        self._tools: List[MCPTool] = []
        self._next_id = 1

    # -- lifecycle -----------------------------------------------------
    def available(self) -> bool:
        return bool(shutil.which(self.command.split()[0]))

    def connect(self) -> bool:
        if not self.available():
            return False
        try:
            self._proc = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            # MCP init handshake
            resp = self._rpc("initialize",
                             {"protocolVersion": "2025-03-26",
                              "capabilities": {},
                              "clientInfo": {"name": "maik", "version": "3.3.1"}})
            self._rpc("notifications/initialized", {})
            return resp is not None
        except Exception:
            return False

    def list_tools(self) -> List[dict]:
        if self._proc is None:
            return []
        with self._lock:
            try:
                resp = self._rpc("tools/list", {})
                if resp and "tools" in resp:
                    self._tools = [MCPTool(t["name"],
                                           t.get("description", ""),
                                           t.get("inputSchema", {}))
                                   for t in resp["tools"]]
            except Exception:
                pass
        return [t.__dict__ if hasattr(t, "__dict__") else t
                for t in self._tools]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> dict:
        if self._proc is None:
            return {"ok": False, "error": "not connected"}
        with self._lock:
            try:
                resp = self._rpc("tools/call",
                                 {"name": tool_name, "arguments": arguments})
                return {"ok": resp is not None, "result": resp}
            except Exception as e:
                return {"ok": False, "error": str(e)[:300]}

    def disconnect(self) -> None:
        with self._lock:
            if self._proc is not None:
                self._proc.terminate()
                self._proc = None

    # -- JSON-RPC ------------------------------------------------------
    def _rpc(self, method: str, params: Any, timeout_s: int = 30) -> Optional[dict]:
        if self._proc is None or self._proc.stdin is None:
            return None
        req = {"jsonrpc": "2.0", "id": self._next_id,
               "method": method, "params": params}
        self._next_id += 1
        self._proc.stdin.write((json.dumps(req) + "\n").encode())
        self._proc.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            line = self._proc.stdout.readline()
            if not line:
                if self._proc.poll() is not None:
                    return None
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") == req["id"]:
                return d.get("result")
        return None


class IntegrationRegistry:
    """All tool plugins + MCP connectors, registered and activatable."""

    def __init__(self, mcp_servers: Optional[Dict[str, dict]] = None):
        self.plugins = {p.name: p for p in DEFAULT_TOOL_PLUGINS}
        self.mcp_defs = mcp_servers or {
            "filesystem": {"command": "npx",
                           "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
            "browser": {"command": "npx",
                        "args": ["-y", "@anthropic/mcp-browser"]},
            "shell": {"command": "npx",
                      "args": ["-y", "@mariozechner/mcp-shell"]},
        }
        self._connectors: Dict[str, MCPConnector] = {}
        self._lock = threading.RLock()

    def register_plugin(self, plugin: ToolPlugin) -> None:
        with self._lock:
            self.plugins[plugin.name] = plugin

    def register_mcp(self, name: str, command: str,
                     args: Optional[List[str]] = None) -> None:
        with self._lock:
            self.mcp_defs[name] = {"command": command, "args": args or []}

    def probe_tool(self, name: str) -> dict:
        p = self.plugins.get(name)
        if p is None:
            return {"available": False, "error": f"unknown plugin {name}"}
        for cmd in p.commands:
            if shutil.which(cmd):
                return {"available": True, "binary": cmd, "note": p.note}
        return {"available": False, "detail": f"not on PATH: {p.commands}"}

    def connect_mcp(self, name: str) -> dict:
        d = self.mcp_defs.get(name)
        if d is None:
            return {"ok": False, "error": f"unknown MCP server {name}"}
        conn = MCPConnector(name, d["command"], d.get("args"))
        if not conn.connect():
            return {"ok": False, "detail": "connect failed (server not installed?)"}
        with self._lock:
            self._connectors[name] = conn
        tools = conn.list_tools()
        return {"ok": True, "tools": tools}

    def call_mcp(self, name: str, tool_name: str,
                 arguments: Optional[Dict[str, Any]] = None) -> dict:
        conn = self._connectors.get(name)
        if conn is None:
            return {"ok": False, "error": f"MCP {name} not connected"}
        return conn.call_tool(tool_name, arguments or {})

    def status(self) -> dict:
        with self._lock:
            return {
                "tool_plugins": {n: self.probe_tool(n)["available"]
                                 for n in self.plugins},
                "mcp_servers": {n: (n in self._connectors)
                                for n in self.mcp_defs},
                "connected_mcp_tools": {
                    n: conn.list_tools() for n, conn in self._connectors.items()},
            }
