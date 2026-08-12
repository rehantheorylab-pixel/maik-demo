"""Futuristic Mind-Map UI — visual agent workflow as interactive tree/graph.

Renders the agent tree as an aesthetic mind map with:
- Color-coded agent roles (Meta=gold, Managers=cyan, Specialists=green, Tools=blue)
- Status indicators (idle=green, busy=yellow, error=red)
- Connection lines between parent/child agents
- Click-to-expand/collapse
- Animated transitions (via threading)
"""
from __future__ import annotations
import json, time, threading
from agent_tree import agent_tree, AgentRole, AgentStatus

# ANSI color codes for terminal/TUI rendering
_STYLE = {
    "meta": {"fg": "bright_yellow", "icon": "👑", "bg": "on_dark_cyan"},
    "manager": {"fg": "cyan", "icon": "📋", "bg": ""},
    "specialist": {"fg": "green", "icon": "⚡", "bg": ""},
    "tool": {"fg": "blue", "icon": "🔧", "bg": ""},
    "idle": "🟢",
    "busy": "🟡",
    "error": "🔴",
    "disabled": "⚪",
}

_COLORS = {
    "meta": "#FFD700",
    "manager": "#00CED1",
    "specialist": "#32CD32",
    "tool": "#4169E1",
    "idle": "#00ff00",
    "busy": "#ffff00",
    "error": "#ff4444",
    "disabled": "#888888",
}


def render_tree_text(detailed: bool = False) -> str:
    """Render agent tree as formatted text (for TUI and console)."""
    structure = agent_tree.get_tree_structure()
    lines = []
    lines.append("")
    lines.append("╔═══════════════════════════════════════════════════════╗")
    lines.append("║            🧠  MAIK AGENT WORKFLOW  🧠              ║")
    lines.append("╚═══════════════════════════════════════════════════════╝")
    lines.append("")

    def _render_node(node: dict, depth: int, is_last: bool):
        prefix = "    " * depth
        if depth > 0:
            prefix += "└─ " if is_last else "├─ "

        role = node["role"]
        style = _STYLE.get(role, _STYLE["tool"])
        status = node["status"]
        status_icon = _STYLE.get(status, "❓")

        capabilities = ""
        if detailed and node.get("capabilities"):
            capabilities = f" [{', '.join(node['capabilities'][:3])}]"

        metrics = node.get("metrics", {})
        metrics_str = ""
        if detailed:
            metrics_str = f" (tasks: {metrics.get('tasks_completed', 0)}/{metrics.get('tasks_failed', 0)}, conf: {metrics.get('avg_confidence', 0):.1%})"

        roles_display = {
            "meta": "META", "manager": "MGR", "specialist": "SPC", "tool": "TOOL"
        }
        role_tag = roles_display.get(role, "???")

        line = (
            f"{prefix}{style['icon']} {status_icon} "
            f"\033[1m{node['name']}\033[0m "
            f"[\033[3m{node['id']}\033[0m] "
            f"(\033[38;5;{_role_color_code(role)}m{role_tag}\033[0m)"
            f"{capabilities}{metrics_str}"
        )
        lines.append(line)

        for i, child in enumerate(node.get("children", [])):
            _render_node(child, depth + 1, i == len(node["children"]) - 1)

    _render_node(structure, 0, True)
    lines.append("")

    stats = agent_tree.stats()
    lines.append(
        f"    📊 {stats['total']} agents | "
        f"🟢{stats['idle']} 🟡{stats['busy']} 🔴{stats['error']} | "
        f"📋{stats['roles']['managers']} managers | "
        f"⚡{stats['roles']['specialists']} specialists | "
        f"🔧{stats['roles']['tools']} tools | "
        f"✓{stats.get('total_tasks', 0)} tasks"
    )
    lines.append("")
    return "\n".join(lines)


def _role_color_code(role: str) -> int:
    return {"meta": 220, "manager": 45, "specialist": 46, "tool": 69}.get(role, 15)


def render_mind_map_json() -> dict:
    """Render full mind map as JSON (for GUI tree widget)."""
    structure = agent_tree.get_tree_structure()

    stats = agent_tree.stats()
    delegations = agent_tree.delegation_history(10)

    return {
        "tree": _node_to_json(structure),
        "stats": stats,
        "delegations": delegations,
    }


def _node_to_json(node: dict) -> dict:
    return {
        "id": node["id"],
        "name": node["name"],
        "role": node["role"],
        "status": node["status"],
        "capabilities": node.get("capabilities", []),
        "metrics": node.get("metrics", {}),
        "style": _STYLE.get(node["role"], _STYLE["tool"]),
        "color": _COLORS.get(node["role"], "#888"),
        "status_color": _COLORS.get(node["status"], "#888"),
        "children": [_node_to_json(c) for c in node.get("children", [])],
    }


class MindMapAnimator:
    """Animates the mind-map for rich visual display.

    Produces progressive frames for terminal or GUI animation.
    """

    def __init__(self):
        self._running = False
        self._frame = 0

    def animate(self, callback, interval: float = 2.0):
        """Run periodic animation updates."""
        self._running = True

        def _loop():
            while self._running:
                self._frame += 1
                data = render_mind_map_json()
                try:
                    callback(data)
                except Exception:
                    pass
                time.sleep(interval)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False


# ── Tkinter mind-map widget ───────────────────────────────────────

try:
    import tkinter as tk
    from tkinter import ttk

    class MindMapWidget(tk.Frame):
        """Interactive mind-map widget for Tkinter GUI.

        Shows agent tree as a collapsible tree with colored nodes.
        """

        def __init__(self, parent, **kwargs):
            super().__init__(parent, **kwargs)
            self._tree = ttk.Treeview(
                self,
                columns=("role", "status", "tasks", "confidence"),
                show="tree headings",
                height=20,
            )
            self._tree.heading("#0", text="Agent")
            self._tree.heading("role", text="Role")
            self._tree.heading("status", text="Status")
            self._tree.heading("tasks", text="Tasks")
            self._tree.heading("confidence", text="Conf.")
            self._tree.column("#0", width=300)
            self._tree.column("role", width=80)
            self._tree.column("status", width=80)
            self._tree.column("tasks", width=60)
            self._tree.column("confidence", width=70)
            self._tree.pack(fill=tk.BOTH, expand=True)
            self._tag_colors()
            self.refresh()

        def _tag_colors(self):
            self._tree.tag_configure("meta", background="#FFF3CD", foreground="#856404")
            self._tree.tag_configure("manager", background="#D1ECF1", foreground="#0C5460")
            self._tree.tag_configure("specialist", background="#D4EDDA", foreground="#155724")
            self._tree.tag_configure("tool", background="#CCE5FF", foreground="#004085")
            self._tree.tag_configure("idle", foreground="green")
            self._tree.tag_configure("busy", foreground="orange")
            self._tree.tag_configure("error", foreground="red")

        def refresh(self):
            for item in self._tree.get_children():
                self._tree.delete(item)
            structure = agent_tree.get_tree_structure()
            self._populate("", structure)

        def _populate(self, parent: str, node: dict):
            name = node["name"]
            role = node["role"]
            status = node["status"]
            metrics = node.get("metrics", {})
            tasks = f"{metrics.get('tasks_completed', 0)}/{metrics.get('tasks_failed', 0)}"
            conf = f"{metrics.get('avg_confidence', 0):.0%}"
            tags = (role, status)
            item = self._tree.insert(
                parent, tk.END, iid=node["id"],
                text=f"{_STYLE.get(role, {}).get('icon', '')} {name} ({node['id']})",
                values=(role.upper(), status.upper(), tasks, conf),
                tags=tags,
            )
            for child in node.get("children", []):
                self._populate(item, child)

except ImportError:
    pass


# ── Console ASCII mind-map ────────────────────────────────────────

def render_ascii_mindmap(detailed: bool = False) -> str:
    """Compact ASCII art mind map."""
    return render_tree_text(detailed)


mindmap = render_mind_map_json
