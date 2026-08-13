"""Organization chart engine (Phase H1).

A fully user-configurable hierarchy: any number of CEOs, each with any number
of managers, each manager with any number of agents, and agents may carry
sub-agents. Every node carries a role, a domain, a budget, a model binding
(seen H2), a system-prompt id (seen H3), and a permission set.

Rules that keep the org sane:
- Only a CEO can add a manager; only a manager can add agents; only an agent
  can add sub-agents (a node deploys strictly one level below itself).
- A CEO sees everything under it (including hidden notebooks, per H4);
  a manager sees its own team; agents see only their public notebook.
- At least 2 CEOs required in the default council; custom orgs may be smaller.
"""

import copy
import enum
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ModelTier

VERSION = "3.1.0"


class NodeLevel(enum.Enum):
    CEO = "ceo"
    MANAGER = "manager"
    AGENT = "agent"
    SUBAGENT = "subagent"


class OrgChartError(ValueError):
    pass


@dataclass
class Powers:
    """Capability flags a node is allowed to exercise."""
    command_run: bool = False
    file_create: bool = False
    screen_read: bool = False
    browser_automation: bool = False
    cli_deploy: bool = False

    def allowed(self, kind: str) -> bool:
        return bool(getattr(self, kind, False))

    @classmethod
    def ceo(cls) -> "Powers":
        return cls(True, True, True, True, True)

    @classmethod
    def manager(cls) -> "Powers":
        return cls(True, True, False, False, True)

    @classmethod
    def agent(cls, commands: bool = False, files: bool = False) -> "Powers":
        return cls(commands, files, False, False, False)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, d: dict) -> "Powers":
        p = cls()
        for k in ("command_run", "file_create", "screen_read", "browser_automation", "cli_deploy"):
            if k in d:
                setattr(p, k, bool(d[k]))
        return p


@dataclass
class OrgNode:
    uid: str
    name: str
    role: str                 # free text, e.g. "code_writer"
    domain: str               # problem domain, e.g. "code"
    level: NodeLevel
    model_binding: Optional[str] = None   # provider/model, e.g. "anthropic/claude-3.5-haiku"
    prompt_id: Optional[str] = None       # per-node prompt override id (H3)
    budget_tokens: int = 30_000
    powers: Powers = field(default_factory=Powers.agent)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "name": self.name, "role": self.role,
            "domain": self.domain, "level": self.level.value,
            "model_binding": self.model_binding, "prompt_id": self.prompt_id,
            "budget_tokens": self.budget_tokens,
            "powers": self.powers.to_dict(), "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OrgNode":
        node = cls(
            uid=d["uid"], name=d["name"], role=d.get("role", d["name"]),
            domain=d.get("domain", ""), level=NodeLevel(d.get("level", "agent")),
            model_binding=d.get("model_binding"), prompt_id=d.get("prompt_id"),
            budget_tokens=int(d.get("budget_tokens", 30_000)),
            powers=Powers.from_dict(d.get("powers", {})),
            metadata=dict(d.get("metadata", {})),
        )
        return node


class OrgChart:
    """Tree of OrgNodes with CEO roots. Parent map + children map; O(1) lookups."""

    LEVEL_ORDER = [NodeLevel.CEO, NodeLevel.MANAGER, NodeLevel.AGENT, NodeLevel.SUBAGENT]

    def __init__(self, name: str = "maik-org", ceos: Optional[List[OrgNode]] = None):
        self.name = name
        self._nodes: Dict[str, OrgNode] = {}
        self._parent: Dict[str, str] = {}   # uid -> parent uid (None for CEOs)
        self._children: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self.created_at = time.time()
        self._seq = 0
        for c in (ceos or []):
            self._add_ceo_node(c)

    # ---------------------------------------------------------------
    @staticmethod
    def _new_uid() -> str:
        return uuid.uuid4().hex[:12]

    # -- council factories ---------------------------------------------
    @classmethod
    def default(cls) -> "OrgChart":
        """Classic 12-CEO council as nodes (keeps maik v3.0 behavior)."""
        from .config import _default_ceos
        return cls("maik-org", ceos=[
            OrgNode(cls._new_uid(), c.name, role=c.domain, domain=c.domain,
                    level=NodeLevel.CEO, model_binding=None,
                    budget_tokens=c.budget_tokens, powers=Powers.ceo())
            for c in _default_ceos()
        ])

    @classmethod
    def light(cls) -> "OrgChart":
        """2-CEO demo org: Code + Research."""
        return cls("maik-org-light", ceos=[
            OrgNode(cls._new_uid(), "Chief Code", role="code", domain="code",
                    level=NodeLevel.CEO, powers=Powers.ceo()),
            OrgNode(cls._new_uid(), "Chief Research", role="research", domain="research",
                    level=NodeLevel.CEO, powers=Powers.ceo()),
        ])

    @classmethod
    def from_spec(cls, spec: dict) -> "OrgChart":
        """Build from a nested JSON spec: {"name": "...", "reports": [{"name", "role",
        "domain", "level", "reports": [...]}]} — full free-form hierarchy."""
        name = spec.get("name", "maik-org")
        ceo_defs = spec.get("ceos") or spec.get("reports") or []
        chart = cls(name)
        for d in ceo_defs:
            chart._from_spec_node(d, NodeLevel.CEO)  # adds CEO itself
        if not chart.ceos():
            raise OrgChartError("Org spec defines no CEOs")
        return chart

    def _from_spec_node(self, d: dict, default_level: NodeLevel) -> OrgNode:
        level = NodeLevel(d.get("level", default_level.value))
        node = OrgNode(self._new_uid(), d["name"], role=d.get("role", d["name"]),
                       domain=d.get("domain", d.get("role", "")), level=level,
                       model_binding=d.get("model_binding"),
                       budget_tokens=int(d.get("budget_tokens", 30_000)),
                       powers=Powers.from_dict(d.get("powers", {})))
        self._add_node(node, parent=None)
        child_level = self._child_level(level)
        if child_level is not None:
            for child in d.get("reports", []) or d.get("agents", []) or []:
                cn = self._from_spec_node(child, child_level)
                self.move(node.uid, cn.uid)
        return node


    def _child_level(self, level: NodeLevel) -> Optional[NodeLevel]:
        idx = self.LEVEL_ORDER.index(level)
        return self.LEVEL_ORDER[idx + 1] if idx + 1 < len(self.LEVEL_ORDER) else None

    # -- mutations -----------------------------------------------------
    def _add_node(self, node: OrgNode, parent: Optional[str]) -> OrgNode:
        if node.uid in self._nodes:
            raise OrgChartError(f"Duplicate node uid {node.uid}")
        with self._lock:
            self._nodes[node.uid] = node
            self._parent[node.uid] = parent
            self._children.setdefault(parent, [])
            if parent is not None:
                if node.uid not in self._children[parent]:
                    self._children[parent].append(node.uid)
        return node

    def _add_ceo_node(self, node: OrgNode) -> OrgNode:
        return self._add_node(node, parent=None)

    def add_manager(self, ceo_uid: str, name: str, role: str, domain: str = "",
                    budget: int = 30_000, powers: Optional[Powers] = None) -> OrgNode:
        ceo = self.node(ceo_uid)
        if ceo is None or ceo.level is not NodeLevel.CEO:
            raise OrgChartError("Only a CEO can add a manager")
        node = OrgNode(self._new_uid(), name, role=role, domain=domain or role,
                       level=NodeLevel.MANAGER, budget_tokens=budget,
                       powers=powers or Powers.manager())
        self._add_node(node, parent=None)
        self.move(ceo_uid, node.uid)
        return node

    def add_agent(self, manager_uid: str, name: str, role: str, domain: str = "",
                  budget: int = 20_000, commands: bool = False,
                  files: bool = False) -> OrgNode:
        mgr = self.node(manager_uid)
        if mgr is None or mgr.level not in (NodeLevel.CEO, NodeLevel.MANAGER):
            raise OrgChartError("Only a CEO or manager can add an agent")
        node = OrgNode(self._new_uid(), name, role=role, domain=domain or role,
                       level=NodeLevel.AGENT, budget_tokens=budget,
                       powers=Powers.agent(commands=commands, files=files))
        self._add_node(node, parent=None)
        self.move(mgr.uid, node.uid)
        return node

    def add_subagent(self, agent_uid: str, name: str, role: str,
                     domain: str = "") -> OrgNode:
        ag = self.node(agent_uid)
        if ag is None or ag.level is not NodeLevel.AGENT:
            raise OrgChartError("Only an agent can add a sub-agent")
        node = OrgNode(self._new_uid(), name, role=role, domain=domain or role,
                       level=NodeLevel.SUBAGENT)
        self._add_node(node, parent=None)
        self.move(ag.uid, node.uid)
        return node

    def remove(self, uid: str) -> None:
        """Remove a node and reparent its children to its parent (or orphan CEOs)."""
        with self._lock:
            if uid not in self._nodes:
                raise OrgChartError(f"No node {uid}")
            parent = self._parent[uid]
            kids = list(self._children.get(uid, []))
            for k in kids:
                self._parent[k] = parent
                if parent is not None:
                    self._children.setdefault(parent, []).append(k)
            self._children.pop(uid, None)
            self._parent.pop(uid, None)
            if parent is not None and uid in self._children[parent]:
                self._children[parent].remove(uid)
            del self._nodes[uid]

    def move(self, parent_uid: Optional[str], child_uid: str) -> None:
        """Attach child under parent (root if None). Validates levels."""
        with self._lock:
            if child_uid not in self._nodes:
                raise OrgChartError(f"No node {child_uid}")
            child = self._nodes[child_uid]
            old = self._parent[child_uid]
            if parent_uid is not None and parent_uid not in self._nodes:
                raise OrgChartError(f"No parent node {parent_uid}")
            # level rule: child must be exactly one level below parent (CEOs attach to root)
            if parent_uid is None:
                if child.level is not NodeLevel.CEO:
                    raise OrgChartError("Only CEO-level nodes attach to the root")
            else:
                pi = self.LEVEL_ORDER.index(self._nodes[parent_uid].level)
                ci = self.LEVEL_ORDER.index(child.level)
                if ci != pi + 1:
                    # CEO may directly host agents (small orgs); everything else
                    # must follow the strict one-level-below rule
                    if not (self._nodes[parent_uid].level is NodeLevel.CEO
                            and child.level is NodeLevel.AGENT):
                        raise OrgChartError(
                            f"{child.level.value} cannot report to "
                            f"{self._nodes[parent_uid].level.value}")
            if old == parent_uid:
                return
            if old is not None:
                self._children[old].remove(child_uid)
            self._parent[child_uid] = parent_uid
            if parent_uid is not None:
                self._children.setdefault(parent_uid, [])
                if child_uid not in self._children[parent_uid]:
                    self._children[parent_uid].append(child_uid)

    # -- queries -------------------------------------------------------
    def node(self, uid: str) -> Optional[OrgNode]:
        return self._nodes.get(uid)

    def find(self, name: str) -> Optional[OrgNode]:
        for n in self._nodes.values():
            if n.name == name:
                return n
        return None

    def nodes(self) -> List[OrgNode]:
        """All nodes in the chart."""
        return list(self._nodes.values())

    def managers(self) -> List[OrgNode]:
        """All manager nodes."""
        return [n for n in self._nodes.values() if n.level is NodeLevel.MANAGER]

    def agents(self) -> List[OrgNode]:
        """All agent nodes (excludes sub-agents)."""
        return [n for n in self._nodes.values() if n.level is NodeLevel.AGENT]

    def ceos(self) -> List[OrgNode]:
        return [n for n in self._nodes.values() if n.level is NodeLevel.CEO]

    def reportees(self, uid: str, direct: bool = False) -> List[OrgNode]:
        if uid not in self._nodes:
            return []
        ids = list(self._children.get(uid, []))
        if direct:
            return [self._nodes[i] for i in ids]
        out = []
        stack = list(ids)
        seen = set()
        while stack:
            i = stack.pop()
            if i in seen or i not in self._nodes:
                continue
            seen.add(i)
            out.append(self._nodes[i])
            stack.extend(self._children.get(i, []))
        return out

    def chain(self, uid: str) -> List[OrgNode]:
        """Path from root CEO down to node."""
        if uid not in self._nodes:
            return []
        path = []
        cur = uid
        while cur is not None:
            path.append(self._nodes[cur])
            cur = self._parent.get(cur)
        return list(reversed(path))

    def ancestors(self, uid: str) -> List[OrgNode]:
        return self.chain(uid)[:-1]

    def siblings(self, uid: str) -> List[OrgNode]:
        if uid not in self._nodes:
            return []
        p = self._parent[uid]
        return [self._nodes[i] for i in self._children.get(p, []) if i != uid]

    def is_ancestor(self, uid_ancestor: str, uid_descendant: str) -> bool:
        seen = set()
        cur = self._parent.get(uid_descendant)
        while cur is not None:
            if cur in seen:
                return False
            seen.add(cur)
            if cur == uid_ancestor:
                return True
            cur = self._parent.get(cur)
        return False

    # -- oversight (H4 hook: CEOs see hidden notebooks) ----------------
    def visible_to(self, node_uid: str) -> List[OrgNode]:
        """All nodes whose public activity node_uid may read. CEOs see all under them."""
        n = self.node(node_uid)
        if n is None:
            return []
        if n.level is NodeLevel.CEO:
            return [n] + self.reportees(node_uid)
        return [n]

    # -- stats ---------------------------------------------------------
    def stats(self) -> dict:
        counts = {lv.value: 0 for lv in NodeLevel}
        for n in self._nodes.values():
            counts[n.level.value] += 1
        return {
            "name": self.name, "total_nodes": len(self._nodes),
            "by_level": counts,
            "depth": max((len(self.chain(u)) - 1 for u in self._nodes), default=0),
        }

    def summary(self) -> dict:
        return {
            "org": self.stats(),
            "ceos": [{"uid": c.uid, "name": c.name, "domain": c.domain,
                      "model_binding": c.model_binding} for c in self.ceos()],
        }

    # -- persistence ---------------------------------------------------
    def to_json(self) -> str:
        with self._lock:
            payload = {
                "version": VERSION, "name": self.name,
                "created_at": self.created_at,
                "nodes": {uid: n.to_dict() for uid, n in self._nodes.items()},
                "parent": {uid: p for uid, p in self._parent.items()},
            }
            return json.dumps(payload, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "OrgChart":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as e:
            raise OrgChartError(f"Invalid org JSON: {e}")
        if d.get("version") != VERSION:
            raise OrgChartError(f"Unsupported org version: {d.get('version')}")
        chart = cls(name=d.get("name", "maik-org"))
        for uid, nd in d.get("nodes", {}).items():
            nd = dict(nd); nd["uid"] = uid
            chart._nodes[uid] = OrgNode.from_dict(nd)
            chart._parent[uid] = d.get("parent", {}).get(uid)
            chart._children.setdefault(chart._parent[uid], [])
            chart._children[chart._parent[uid]].append(uid)
        return chart

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: Path) -> "OrgChart":
        return cls.from_json(Path(path).read_text())
