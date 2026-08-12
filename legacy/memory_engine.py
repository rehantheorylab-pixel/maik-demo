import time
import json
import hashlib
import heapq
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class L1Memory:
    capacity: int = 50
    ttl_s: float = 300.0
    _entries: list = field(default_factory=list)

    def store(self, key: str, value: str, metadata: Optional[dict] = None):
        self._entries.append({
            "key": key, "value": value, "metadata": metadata or {},
            "stored_at": time.time(), "access_count": 0,
        })
        if len(self._entries) > self.capacity:
            self._entries.sort(key=lambda e: (e["access_count"], -e["stored_at"]))
            self._entries = self._entries[:self.capacity]

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        scored = []
        now = time.time()
        qset = set(query.lower().split())
        for e in self._entries:
            if now - e["stored_at"] > self.ttl_s:
                continue
            eset = set(e["key"].lower().split()) | set(e["value"].lower().split()[:10])
            sim = len(qset & eset) / max(len(qset | eset), 1)
            scored.append((sim, e))
            e["access_count"] += 1
        scored.sort(key=lambda x: -x[0])
        return [{"key": s[1]["key"], "value": s[1]["value"][:300], "metadata": s[1]["metadata"], "score": s[0]} for s in scored[:top_k]]

@dataclass
class L2Memory:
    consolidation_interval: float = 600.0
    min_confidence: float = 0.7
    min_access: int = 3
    _entries: list = field(default_factory=list)

    def consider(self, entry: dict) -> Optional[dict]:
        if entry.get("access_count", 0) >= self.min_access and entry.get("metadata", {}).get("confidence", 0) >= self.min_confidence:
            consolidated = {**entry, "consolidated_at": time.time(), "tier": "L2"}
            self._entries.append(consolidated)
            return consolidated
        return None

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        qset = set(query.lower().split())
        scored = []
        for e in self._entries:
            sim = len(qset & set(e["key"].lower().split())) / max(len(qset | set(e["key"].lower().split())), 1)
            scored.append((sim, e))
        scored.sort(key=lambda x: -x[0])
        return [{"key": s[1]["key"], "value": s[1]["value"][:300], "confidence": s[1].get("metadata", {}).get("confidence", 0), "score": s[0]} for s in scored[:top_k]]

@dataclass
class L3Memory:
    _entries: list = field(default_factory=list)

    def archive(self, entry: dict):
        self._entries.append({**entry, "archived_at": time.time(), "tier": "L3"})

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        qset = set(query.lower().split())
        scored = []
        for e in self._entries:
            sim = len(qset & set(e["key"].lower().split())) / max(len(qset | set(e["key"].lower().split())), 1)
            scored.append((sim, e))
        scored.sort(key=lambda x: -x[0])
        return [{"key": s[1]["key"], "value": s[1]["value"][:300], "archived_at": s[1]["archived_at"], "score": s[0]} for s in scored[:top_k]]

class ThoughtVDB:
    def __init__(self, max_thoughts: int = 200):
        self._thoughts: list[dict] = []
        self._max_thoughts = max_thoughts
        self._hatching_pool: list[dict] = []

    def inject(self, agent_id: str, thought: str, tags: Optional[list[str]] = None, confidence: float = 0.5):
        entry = {
            "id": hashlib.md5(f"{time.time()}:{thought}".encode()).hexdigest()[:8],
            "agent": agent_id, "thought": thought, "tags": tags or [],
            "confidence": confidence, "created_at": time.time(),
            "heat": 0.0,
        }
        self._thoughts.append(entry)
        if len(self._thoughts) > self._max_thoughts:
            self._thoughts.sort(key=lambda t: t["heat"] - (time.time() - t["created_at"]) / 3600)
            self._thoughts = self._thoughts[:self._max_thoughts]

    def query(self, topic: str, top_k: int = 5) -> list[dict]:
        tset = set(topic.lower().split())
        scored = []
        for t in self._thoughts:
            tset2 = set(t["thought"].lower().split()) | set(t["tags"])
            sim = len(tset & tset2) / max(len(tset | tset2), 1)
            scored.append((sim * t["confidence"], t))
        scored.sort(key=lambda x: -x[0])
        return [{"id": s[1]["id"], "thought": s[1]["thought"][:200], "tags": s[1]["tags"], "confidence": s[1]["confidence"], "score": s[0]} for s in scored[:top_k]]

    def incubate(self, thought_id: str, heat_amount: float = 0.1):
        for t in self._thoughts:
            if t["id"] == thought_id:
                t["heat"] += heat_amount
                if t["heat"] >= 1.0:
                    self._hatching_pool.append(t)
                    t["heat"] = 0.0
                return True
        return False

    def hatch(self) -> Optional[dict]:
        if self._hatching_pool:
            return self._hatching_pool.pop(0)
        return None

    def consolidate(self) -> int:
        cutoff = time.time() - 3600
        stale = [t for t in self._thoughts if t["created_at"] < cutoff and t["heat"] < 0.3]
        self._thoughts = [t for t in self._thoughts if t not in stale]
        return len(stale)

l1_memory = L1Memory()
l2_memory = L2Memory()
l3_memory = L3Memory()
thought_vdb = ThoughtVDB()
