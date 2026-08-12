"""Agent Tree — hierarchical 10+ agent management with intelligent delegation.

Architecture:
- Root: Meta-controller (orchestrates everything)
- Level 1: Domain Managers (Research, Code, Media, Network, Analysis, System)
- Level 2: Specialized Agents (BrowserAgent, ComputerUse, PixelVision, FileAccess, etc.)
- Level 3: Tool Agents (GitHub, CLI Plugins, APIs, etc.)
- Intelligent delegation: parent analyzes task, picks best child agent
- Cross-agent communication via shared event bus
"""
from __future__ import annotations
import json, time, uuid, threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"


class AgentRole(Enum):
    META = "meta"
    MANAGER = "manager"
    SPECIALIST = "specialist"
    TOOL = "tool"


@dataclass
class AgentNode:
    """A node in the agent tree."""
    id: str
    name: str
    role: AgentRole
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    parent_id: Optional[str] = None
    children: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=lambda: {
        "tasks_completed": 0, "tasks_failed": 0,
        "avg_confidence": 0.0, "avg_latency": 0.0,
        "last_active": 0,
    })
    config: dict = field(default_factory=dict)


# ── Agent Definitions ─────────────────────────────────────────────

AGENT_DEFINITIONS = [
    # Meta-controller (root)
    AgentNode("meta", "Meta Controller", AgentRole.META,
              "Orchestrates all agents, routes tasks, manages delegation",
              ["orchestration", "delegation", "planning", "routing"]),

    # Level 1: Domain Managers
    AgentNode("research_mgr", "Research Manager", AgentRole.MANAGER,
              "Manages web research, data extraction, academic search",
              ["research_planning", "source_selection", "fact_checking"],
              parent_id="meta"),
    AgentNode("code_mgr", "Code Manager", AgentRole.MANAGER,
              "Manages code analysis, generation, debugging",
              ["code_review", "architecture", "refactoring"],
              parent_id="meta"),
    AgentNode("media_mgr", "Media Manager", AgentRole.MANAGER,
              "Manages screen/media processing, vision, audio",
              ["vision_planning", "media_processing"],
              parent_id="meta"),
    AgentNode("network_mgr", "Network Manager", AgentRole.MANAGER,
              "Manages HTTP requests, APIs, web scraping",
              ["http_planning", "api_routing", "scraping"],
              parent_id="meta"),
    AgentNode("data_mgr", "Data Manager", AgentRole.MANAGER,
              "Manages data processing, transformation, storage",
              ["data_pipeline", "format_conversion", "storage"],
              parent_id="meta"),
    AgentNode("sys_mgr", "System Manager", AgentRole.MANAGER,
              "Manages file access, process execution, OS operations",
              ["file_ops", "process_mgmt", "environment"],
              parent_id="meta"),

    # Level 2: Specialized Agents
    AgentNode("browser", "Browser Agent", AgentRole.SPECIALIST,
              "Web automation with Playwright: navigate, click, type, extract",
              ["web_navigation", "dom_extraction", "screenshot", "form_fill"],
              parent_id="media_mgr"),
    AgentNode("computer_use", "Computer Use Agent", AgentRole.SPECIALIST,
              "Desktop automation: mouse, keyboard, window management, OCR",
              ["mouse_control", "keyboard", "window_mgmt", "app_launch"],
              parent_id="media_mgr"),
    AgentNode("pixel_vision", "Pixel Vision Agent", AgentRole.SPECIALIST,
              "Screen perception: icon detection, color analysis, OCR, layout",
              ["object_detection", "ocr", "color_analysis", "layout_detection"],
              parent_id="media_mgr"),
    AgentNode("web_research", "Web Research Agent", AgentRole.SPECIALIST,
              "Deep web research: multi-source extraction, fact synthesis",
              ["web_search", "content_extraction", "citation", "synthesis"],
              parent_id="research_mgr"),
    AgentNode("file_access", "File Access Agent", AgentRole.SPECIALIST,
              "File system operations: search, grep, glob, diff, tree view",
              ["file_search", "grep", "glob", "diff", "tree_view"],
              parent_id="sys_mgr"),
    AgentNode("code_analysis", "Code Analysis Engine", AgentRole.SPECIALIST,
              "Static code analysis: complexity, dependencies, refactoring",
              ["complexity", "dependency_graph", "dead_code", "refactor"],
              parent_id="code_mgr"),

    # Level 3: Tool Agents
    AgentNode("github", "GitHub Integration", AgentRole.TOOL,
              "GitHub API: repos, issues, PRs, gists, search",
              ["repo_mgmt", "issue_tracking", "pr_mgmt", "code_search"],
              parent_id="code_mgr"),
    AgentNode("api_router", "API Router", AgentRole.TOOL,
              "Intelligent multi-API routing: GPT, Claude, Gemini, etc.",
              ["llm_routing", "model_selection", "fallback", "caching"],
              parent_id="network_mgr"),
    AgentNode("cli_plugins", "CLI Plugin System", AgentRole.TOOL,
              "Run any CLI tool as plugin: ffmpeg, curl, jq, docker, etc.",
              ["plugin_exec", "tool_detection", "pipeline", "chain"],
              parent_id="sys_mgr"),
    AgentNode("auth_manager", "Auth Manager", AgentRole.TOOL,
              "Secure credential storage, API key management, .env",
              ["key_storage", "encryption", "dotenv", "rotation"],
              parent_id="sys_mgr"),
    AgentNode("session_compactor", "Session Compactor", AgentRole.TOOL,
              "Session archiving, compression, logging, summarization",
              ["compaction", "archival", "search", "summary"],
              parent_id="data_mgr"),
]


class AgentTree:
    """Hierarchical agent tree with intelligent delegation.

    Features:
    - Tree of 19 agents (1 meta, 6 managers, 7 specialists, 5 tools)
    - Status tracking per agent
    - Intelligent delegation: task → best agent path
    - Cross-agent event broadcast
    - Performance metrics per agent
    """

    def __init__(self):
        self._agents: dict[str, AgentNode] = {}
        self._event_bus: list[dict] = []
        self._lock = threading.Lock()
        self._init_agents()
        self._delegation_history: list[dict] = []

    def _init_agents(self):
        for agent in AGENT_DEFINITIONS:
            self._agents[agent.id] = agent
        # Build children lists from parent_id
        for agent in self._agents.values():
            if agent.parent_id and agent.parent_id in self._agents:
                parent = self._agents[agent.parent_id]
                if agent.id not in parent.children:
                    parent.children.append(agent.id)

    def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        return self._agents.get(agent_id)

    def list_agents(self, role: Optional[str] = None) -> list[dict]:
        agents = self._agents.values()
        if role:
            agents = [a for a in agents if a.role.value == role]
        return [
            {
                "id": a.id, "name": a.name, "role": a.role.value,
                "status": a.status.value, "description": a.description,
                "capabilities": a.capabilities,
                "parent_id": a.parent_id, "children": a.children,
                "metrics": a.metrics,
            }
            for a in sorted(agents, key=lambda x: x.id)
        ]

    def get_children(self, agent_id: str) -> list[dict]:
        """Get direct children of an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return []
        return self.list_agents_by_ids(agent.children)

    def list_agents_by_ids(self, ids: list[str]) -> list[dict]:
        return [self._agents[aid] for aid in ids if aid in self._agents]

    def get_tree_structure(self) -> dict:
        """Get full tree hierarchy as nested dict."""
        def _build(node_id: str) -> dict:
            agent = self._agents.get(node_id)
            if not agent:
                return {}
            return {
                "id": agent.id, "name": agent.name, "role": agent.role.value,
                "status": agent.status.value,
                "capabilities": agent.capabilities,
                "metrics": agent.metrics,
                "children": [_build(cid) for cid in agent.children],
            }
        return _build("meta")

    def set_status(self, agent_id: str, status: AgentStatus):
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = status
            if status == AgentStatus.BUSY:
                agent.metrics["last_active"] = time.time()

    def record_completion(self, agent_id: str, success: bool, confidence: float = 0.0, latency: float = 0.0):
        agent = self._agents.get(agent_id)
        if agent:
            if success:
                agent.metrics["tasks_completed"] += 1
            else:
                agent.metrics["tasks_failed"] += 1
            agent.metrics["avg_confidence"] = (
                agent.metrics["avg_confidence"] * 0.9 + confidence * 0.1
            )
            agent.metrics["avg_latency"] = (
                agent.metrics["avg_latency"] * 0.9 + latency * 0.1
            )
            agent.status = AgentStatus.IDLE

    # ── Delegation ─────────────────────────────────────────────────

    def delegate(self, task: str, domain: str = "") -> dict:
        """Intelligently route a task to the best agent path."""
        task_lower = task.lower()
        # Keyword-based routing
        routing_map: list[tuple[list[str], str]] = [
            (["browser", "web", "navigate", "http", "url", "page", "click", "type"], "browser"),
            (["computer", "mouse", "keyboard", "click", "drag", "window", "desktop", "screen", "notepad"], "computer_use"),
            (["vision", "see", "look", "icon", "button", "color", "pixel", "ocr", "image"], "pixel_vision"),
            (["research", "search", "find", "lookup", "information", "web"], "web_research"),
            (["file", "search", "grep", "glob", "find", "read", "write", "disk"], "file_access"),
            (["code", "analyze", "complexity", "refactor", "dead", "function", "class"], "code_analysis"),
            (["github", "repo", "issue", "pr", "commit", "push", "pull"], "github"),
            (["api", "gpt", "claude", "gemini", "llm", "model", "route"], "api_router"),
            (["cli", "plugin", "ffmpeg", "curl", "docker", "jq", "tool"], "cli_plugins"),
            (["auth", "key", "token", "password", "credential", ".env"], "auth_manager"),
            (["compact", "archive", "compress", "session", "log"], "session_compactor"),
        ]
        scored: list[tuple[int, str]] = []
        for keywords, agent_id in routing_map:
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scored.append((score, agent_id))
        if scored:
            scored.sort(key=lambda x: -x[0])
            best_agent_id = scored[0][1]
        else:
            best_agent_id = "meta"  # Fallback to meta-controller

        entry = {
            "time": time.time(), "task": task[:80], "domain": domain,
            "delegated_to": best_agent_id, "id": str(uuid.uuid4())[:8],
        }
        self._delegation_history.append(entry)
        # Find the agent path
        agent = self._agents.get(best_agent_id)
        path = [best_agent_id]
        if agent:
            parent = agent.parent_id
            while parent:
                path.insert(0, parent)
                parent = self._agents.get(parent)
                parent = parent.parent_id if parent else None
        entry["path"] = path
        return entry

    def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all agents (async)."""
        event = {
            "id": str(uuid.uuid4())[:8],
            "type": event_type, "data": data,
            "time": time.time(),
        }
        self._event_bus.append(event)
        # Keep only last 100 events
        if len(self._event_bus) > 100:
            self._event_bus = self._event_bus[-100:]

    def get_events(self, event_type: str = "", limit: int = 20) -> list[dict]:
        events = self._event_bus
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]

    def agent_summary(self) -> str:
        """Human-readable tree summary (ASCII-safe)."""
        out = []
        out.append("+======================================+")
        out.append("|         AGENT TREE OVERVIEW          |")
        out.append("+======================================+")
        def _walk(node_id: str, depth: int):
            agent = self._agents.get(node_id)
            if not agent:
                return
            prefix = "  " * depth + ("L- " if depth > 0 else "")
            status_icon = {"idle": "[I]", "busy": "[B]", "error": "[E]", "disabled": "[D]"}
            icon = status_icon.get(agent.status.value, "[?]")
            out.append(f"{prefix}{icon} {agent.name} ({agent.id}) [{agent.role.value}]")
            for child_id in agent.children:
                _walk(child_id, depth + 1)
        _walk("meta", 0)
        out.append("")
        totals = self.stats()
        out.append(f"Total: {totals['total']} | Idle: {totals['idle']} | Busy: {totals['busy']} | "
                   f"Tasks: {totals['total_tasks']} | Delegations: {len(self._delegation_history)}")
        return "\n".join(out)

    def delegation_history(self, limit: int = 20) -> list[dict]:
        return self._delegation_history[-limit:]

    def stats(self) -> dict:
        """Full statistics."""
        statuses = {"idle": 0, "busy": 0, "error": 0, "disabled": 0}
        total_tasks = 0
        for agent in self._agents.values():
            s = agent.status.value
            if s in statuses:
                statuses[s] += 1
            total_tasks += agent.metrics["tasks_completed"] + agent.metrics["tasks_failed"]
        return {
            "total": len(self._agents),
            "roles": {
                "meta": sum(1 for a in self._agents.values() if a.role == AgentRole.META),
                "managers": sum(1 for a in self._agents.values() if a.role == AgentRole.MANAGER),
                "specialists": sum(1 for a in self._agents.values() if a.role == AgentRole.SPECIALIST),
                "tools": sum(1 for a in self._agents.values() if a.role == AgentRole.TOOL),
            },
            **statuses,
            "total_tasks": total_tasks,
            "delegations": len(self._delegation_history),
        }


agent_tree = AgentTree()
