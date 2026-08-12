import time, hashlib, uuid
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LibraryEntry:
    name: str
    version: str = "0.1.0"
    content: str = ""
    author: str = ""
    domain: str = ""
    visibility: str = "internal"
    created_at: float = field(default_factory=time.time)
    usage_count: int = 0
    quality_score: float = 0.7

class CorporateLibrary:
    def __init__(self):
        self._libraries: dict[str, LibraryEntry] = {}
        self._agents: dict[str, str] = {}

    def register_agent(self, agent_id: str, role: str = "specialist"):
        self._agents[agent_id] = role

    def contribute(self, agent_id: str, name: str, content: str,
                   domain: str = "", version: str = "0.1.0",
                   visibility: str = "internal") -> Optional[str]:
        role = self._agents.get(agent_id, "specialist")
        if visibility == "protected" and role not in ("exec", "ceo"):
            return None
        lib_id = hashlib.md5(f"{name}:{version}".encode()).hexdigest()[:8]
        self._libraries[lib_id] = LibraryEntry(
            name=name, version=version, content=content,
            author=agent_id, domain=domain, visibility=visibility,
        )
        return lib_id

    def search(self, query: str, domain: str = "", top_k: int = 5) -> list[dict]:
        qset = set(query.lower().split())
        scored = []
        for lib_id, entry in self._libraries.items():
            if domain and entry.domain != domain:
                continue
            eset = set(entry.name.lower().split()) | set(entry.domain.lower().split())
            sim = len(qset & eset) / max(len(qset | eset), 1)
            scored.append((sim * entry.quality_score, lib_id, entry))
        scored.sort(key=lambda x: -x[0])
        return [
            {"id": s[1], "name": s[2].name, "version": s[2].version,
             "domain": s[2].domain, "author": s[2].author,
             "quality": s[2].quality_score, "usage": s[2].usage_count,
             "score": s[0]}
            for s in scored[:top_k]
        ]

    def use_library(self, lib_id: str) -> Optional[str]:
        entry = self._libraries.get(lib_id)
        if entry:
            entry.usage_count += 1
            return entry.content
        return None

    def list_by_agent(self, agent_id: str) -> list[dict]:
        return [{"id": lid, "name": e.name, "version": e.version, "usage": e.usage_count}
                for lid, e in self._libraries.items() if e.author == agent_id]

    def stats(self) -> dict:
        return {
            "total_libraries": len(self._libraries),
            "total_agents": len(self._agents),
            "total_usage": sum(e.usage_count for e in self._libraries.values()),
            "avg_quality": sum(e.quality_score for e in self._libraries.values()) / max(len(self._libraries), 1),
        }

class PermissionSystem:
    def __init__(self):
        self._permissions: dict[str, set[str]] = {
            "ceo": {"deploy", "modify_safety", "modify_budget", "access_all", "delete_library", "approve"},
            "exec": {"approve", "spawn_agent", "access_notes", "contribute_protected", "delete_own"},
            "manager": {"spawn_agent", "access_notes", "contribute", "review"},
            "specialist": {"execute", "contribute", "read_public"},
        }

    def check(self, role: str, action: str) -> bool:
        return action in self._permissions.get(role, set())

    def grant(self, role: str, action: str):
        self._permissions.setdefault(role, set()).add(action)

    def revoke(self, role: str, action: str):
        self._permissions.get(role, set()).discard(action)

@dataclass
class OrgNode:
    id: str
    name: str
    node_type: str = "agent"
    parent_id: str = ""
    children: list = field(default_factory=list)
    metadata: dict = field(default_factory=lambda: {
        "status": "idle", "tasks": 0, "elo": 1000, "agent_count": 0, "descendant_count": 0
    })

class OrgChart:
    def __init__(self):
        self._nodes: dict[str, OrgNode] = {}

    def add_node(self, node_id: str, name: str, node_type: str = "agent", parent_id: str = "") -> OrgNode:
        node = OrgNode(id=node_id, name=name, node_type=node_type, parent_id=parent_id)
        self._nodes[node_id] = node
        if parent_id and parent_id in self._nodes:
            if node_id not in self._nodes[parent_id].children:
                self._nodes[parent_id].children.append(node_id)
        self._link_agent(node_id, node_type)
        self._recalc_counts()
        return node

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        node = self._nodes[node_id]
        if node.parent_id and node.parent_id in self._nodes:
            parent = self._nodes[node.parent_id]
            if node_id in parent.children:
                parent.children.remove(node_id)
        self._remove_descendants(node_id)
        del self._nodes[node_id]
        self._recalc_counts()
        return True

    def _remove_descendants(self, node_id: str):
        if node_id not in self._nodes:
            return
        for cid in list(self._nodes[node_id].children):
            self._remove_descendants(cid)
            if cid in self._nodes:
                del self._nodes[cid]

    def add_child(self, parent_id: str, child_id: str, child_name: str, child_type: str = "agent") -> Optional[OrgNode]:
        return self.add_node(child_id, child_name, child_type, parent_id)

    def get_node(self, node_id: str) -> Optional[OrgNode]:
        return self._nodes.get(node_id)

    def get_children(self, node_id: str) -> list[OrgNode]:
        node = self._nodes.get(node_id)
        if not node:
            return []
        return [self._nodes[cid] for cid in node.children if cid in self._nodes]

    def get_descendant_count(self, node_id: str) -> int:
        count = 0
        node = self._nodes.get(node_id)
        if not node:
            return 0
        for cid in node.children:
            count += 1
            count += self.get_descendant_count(cid)
        return count

    def get_sub_agent_count(self, node_id: str, agent_type: str = "") -> int:
        count = 0
        node = self._nodes.get(node_id)
        if not node:
            return 0
        for cid in node.children:
            child = self._nodes.get(cid)
            if child:
                if not agent_type or child.node_type == agent_type:
                    count += 1
                count += self.get_sub_agent_count(cid, agent_type)
        return count

    def _link_agent(self, node_id: str, node_type: str):
        agent_tracker.register(node_id, node_type)

    def _recalc_counts(self):
        for node_id in list(self._nodes.keys()):
            node = self._nodes.get(node_id)
            if not node:
                continue
            node.metadata["descendant_count"] = self.get_descendant_count(node_id)

    def add_ceo(self, ceo_id: str, name: str) -> OrgNode:
        return self.add_node(ceo_id, name, "ceo")

    def remove_ceo(self, ceo_id: str) -> bool:
        return self.remove_node(ceo_id)

    def add_manager(self, ceo_id: str, mgr_id: str, mgr_name: str) -> Optional[OrgNode]:
        ceo = self._nodes.get(ceo_id)
        if not ceo or ceo.node_type != "ceo":
            return None
        return self.add_node(mgr_id, mgr_name, "manager", ceo_id)

    def remove_manager(self, ceo_id: str, mgr_id: str) -> bool:
        mgr = self._nodes.get(mgr_id)
        if not mgr or mgr.parent_id != ceo_id:
            return False
        return self.remove_node(mgr_id)

    def add_employee(self, ceo_id: str, mgr_id: str, emp_id: str, emp_name: str, role: str = "employee") -> Optional[OrgNode]:
        mgr = self._nodes.get(mgr_id)
        if not mgr:
            return None
        return self.add_node(emp_id, emp_name, role, mgr_id)

    def remove_employee(self, ceo_id: str, mgr_id: str, emp_id: str) -> bool:
        emp = self._nodes.get(emp_id)
        if not emp or emp.parent_id != mgr_id:
            return False
        return self.remove_node(emp_id)

    def get_mind_map(self) -> dict:
        result = {}
        for node_id, node in self._nodes.items():
            if node.node_type == "ceo":
                result[node_id] = self._node_to_dict(node)
        return result

    def _node_to_dict(self, node: OrgNode) -> dict:
        return {
            "name": node.name,
            "type": node.node_type,
            "children": {cid: self._node_to_dict(self._nodes[cid]) for cid in node.children if cid in self._nodes},
            "descendants": node.metadata.get("descendant_count", 0),
            "sub_agents": len(node.children),
            "agent_data": self._get_agent_data(node.id),
        }

    def _get_agent_data(self, agent_id: str) -> dict:
        stats = agent_tracker.stats(agent_id)
        if stats:
            return {"elo": stats.get("elo", 1000), "tasks": stats.get("tasks", 0),
                    "success_rate": stats.get("successes", 0) / max(stats.get("tasks", 0), 1),
                    "status": stats.get("status", "idle")}
        return {"elo": 1000, "tasks": 0, "success_rate": 0.0, "status": "unknown"}

    def to_tree(self, node_id: str = "") -> dict:
        if node_id:
            node = self._nodes.get(node_id)
            if node:
                return {node.id: self._node_to_dict(node)}
            return {}
        result = {}
        for nid, node in self._nodes.items():
            if node.node_type == "ceo":
                result[nid] = self._node_to_dict(node)
        return result

    def total_count(self) -> dict:
        ceos = sum(1 for n in self._nodes.values() if n.node_type == "ceo")
        mgrs = sum(1 for n in self._nodes.values() if n.node_type == "manager")
        agents = sum(1 for n in self._nodes.values() if n.node_type == "agent")
        employees = sum(1 for n in self._nodes.values() if n.node_type == "employee")
        return {"ceos": ceos, "managers": mgrs, "employees": employees, "agents": agents,
                "total": len(self._nodes), "sub_agents": agents + employees}

    def find_by_type(self, node_type: str) -> list[OrgNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def find_by_name(self, name: str) -> list[OrgNode]:
        return [n for n in self._nodes.values() if name.lower() in n.name.lower()]

org_chart = OrgChart()

class AgentTracker:
    def __init__(self):
        self._agents: dict[str, dict] = {}

    def register(self, agent_id: str, role: str, model: str = ""):
        if agent_id in self._agents:
            return
        self._agents[agent_id] = {
            "role": role, "model": model, "tasks": 0, "successes": 0,
            "failures": 0, "total_confidence": 0.0, "elo": 1000.0,
            "status": "idle", "last_active": time.time(),
        }

    def record_task(self, agent_id: str, success: bool, confidence: float = 0.5):
        a = self._agents.get(agent_id)
        if not a:
            return
        a["tasks"] += 1
        if success:
            a["successes"] += 1
        else:
            a["failures"] += 1
        a["total_confidence"] += confidence
        a["last_active"] = time.time()
        n = a["tasks"]
        a["elo"] = a["elo"] + (20 if success else -15) * (1 - a["elo"] / 2000)

    def set_status(self, agent_id: str, status: str):
        a = self._agents.get(agent_id)
        if a:
            a["status"] = status

    def stats(self, agent_id: str = "") -> dict:
        if agent_id:
            return self._agents.get(agent_id, {})
        total = len(self._agents)
        active = sum(1 for a in self._agents.values() if a["status"] == "busy")
        avg_elo = sum(a["elo"] for a in self._agents.values()) / max(total, 1)
        avg_success = sum(a["successes"] for a in self._agents.values()) / max(sum(a["tasks"] for a in self._agents.values()), 1)
        return {
            "total": total, "active": active, "idle": total - active,
            "avg_elo": round(avg_elo, 1), "avg_success_rate": round(avg_success, 3),
            "agents": {aid: {"role": a["role"], "elo": round(a["elo"], 1),
                            "tasks": a["tasks"], "success_rate": a["successes"]/max(a["tasks"],1),
                            "status": a["status"]}
                      for aid, a in self._agents.items()},
        }

    def leaderboard(self, top_k: int = 10) -> list[dict]:
        sorted_agents = sorted(self._agents.items(), key=lambda x: -x[1]["elo"])
        return [{"id": aid, "role": a["role"], "elo": round(a["elo"], 1),
                 "tasks": a["tasks"], "success_rate": a["successes"]/max(a["tasks"],1),
                 "status": a["status"]}
                for aid, a in sorted_agents[:top_k]]

    def linked_org_stats(self, node_id: str) -> dict:
        a = self._agents.get(node_id, {})
        org_node = org_chart.get_node(node_id)
        return {
            "id": node_id, "role": a.get("role", "?"), "elo": a.get("elo", 1000),
            "tasks": a.get("tasks", 0), "success_rate": a.get("successes", 0) / max(a.get("tasks", 0), 1),
            "status": a.get("status", "idle"),
            "sub_agents": len(org_node.children) if org_node else 0,
            "descendants": org_node.metadata.get("descendant_count", 0) if org_node else 0,
        }

agent_tracker = AgentTracker()
corp_library = CorporateLibrary()
perm_system = PermissionSystem()
