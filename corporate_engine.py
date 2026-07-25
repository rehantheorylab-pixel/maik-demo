import time
import hashlib
import uuid
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
class OrgEmployee:
    id: str
    name: str
    role: str
    parent_id: str = ""
    skills: list = field(default_factory=list)
    status: str = "idle"
    tasks_completed: int = 0
    success_rate: float = 1.0

@dataclass
class OrgManager:
    id: str
    name: str
    parent_ceo_id: str
    employees: list = field(default_factory=list)

@dataclass
class OrgCEO:
    id: str
    name: str
    managers: list = field(default_factory=list)

class OrgChart:
    def __init__(self):
        self.ceos: dict[str, OrgCEO] = {}

    def add_ceo(self, ceo_id: str, name: str) -> OrgCEO:
        o = OrgCEO(ceo_id, name)
        self.ceos[ceo_id] = o
        return o

    def remove_ceo(self, ceo_id: str) -> bool:
        return self.ceos.pop(ceo_id, None) is not None

    def add_manager(self, ceo_id: str, mgr_id: str, mgr_name: str) -> Optional[OrgManager]:
        ceo = self.ceos.get(ceo_id)
        if not ceo:
            return None
        m = OrgManager(mgr_id, mgr_name, ceo_id)
        ceo.managers.append(m)
        return m

    def remove_manager(self, ceo_id: str, mgr_id: str) -> bool:
        ceo = self.ceos.get(ceo_id)
        if not ceo:
            return False
        for i, m in enumerate(ceo.managers):
            if m.id == mgr_id:
                ceo.managers.pop(i)
                return True
        return False

    def add_employee(self, ceo_id: str, mgr_id: str, emp_id: str, emp_name: str, role: str = "employee") -> Optional[OrgEmployee]:
        ceo = self.ceos.get(ceo_id)
        if not ceo:
            return None
        for m in ceo.managers:
            if m.id == mgr_id:
                e = OrgEmployee(emp_id, emp_name, role, mgr_id)
                m.employees.append(e)
                return e
        return None

    def remove_employee(self, ceo_id: str, mgr_id: str, emp_id: str) -> bool:
        ceo = self.ceos.get(ceo_id)
        if not ceo:
            return False
        for m in ceo.managers:
            if m.id == mgr_id:
                for i, e in enumerate(m.employees):
                    if e.id == emp_id:
                        m.employees.pop(i)
                        return True
        return False

    def get_mind_map(self) -> dict:
        result = {}
        for ceo_id, ceo in self.ceos.items():
            mgrs = {}
            for m in ceo.managers:
                mgrs[m.id] = {
                    "name": m.name,
                    "employees": [{"id": e.id, "name": e.name, "role": e.role, "status": e.status, "tasks": e.tasks_completed} for e in m.employees]
                }
            result[ceo_id] = {"name": ceo.name, "managers": mgrs}
        return result

    def to_tree(self, ceo_id: str = "") -> dict:
        if ceo_id:
            result = {}
            ceo = self.ceos.get(ceo_id)
            if ceo:
                result[ceo.id] = {"name": ceo.name, "children": {}}
                for m in ceo.managers:
                    result[ceo.id]["children"][m.id] = {"name": m.name, "children": {}}
                    for e in m.employees:
                        result[ceo.id]["children"][m.id]["children"][e.id] = {"name": e.name, "role": e.role}
            return result
        return self.get_mind_map()

    def total_count(self) -> dict:
        ceos = len(self.ceos)
        mgrs = sum(len(c.managers) for c in self.ceos.values())
        emps = sum(len(e.employees) for c in self.ceos.values() for e in c.managers)
        return {"ceos": ceos, "managers": mgrs, "employees": emps}

org_chart = OrgChart()

class AgentTracker:
    def __init__(self):
        self._agents: dict[str, dict] = {}

    def register(self, agent_id: str, role: str, model: str = ""):
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

agent_tracker = AgentTracker()
corp_library = CorporateLibrary()
perm_system = PermissionSystem()
