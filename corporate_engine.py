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

corp_library = CorporateLibrary()
perm_system = PermissionSystem()
