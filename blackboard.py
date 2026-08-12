import time
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from memory_engine import thought_vdb, l1_memory

@dataclass
class Note:
    agent_id: str
    content: str
    visibility: str = "public"
    created_at: float = field(default_factory=time.time)
    confidence: float = 1.0

class InternalNotes:
    def __init__(self):
        self._notes: dict[str, list[Note]] = {}

    def write(self, agent_id: str, content: str, visibility: str = "public", confidence: float = 1.0):
        self._notes.setdefault(agent_id, []).append(Note(agent_id, content, visibility, time.time(), confidence))

    def read(self, agent_id: str, requester_id: str = "", requester_depth: int = 99) -> list[Note]:
        notes = self._notes.get(agent_id, [])
        result = []
        for n in notes:
            if n.visibility == "public":
                result.append(n)
            elif n.visibility == "ceo" and requester_depth == 0:
                result.append(n)
            elif n.visibility == "private" and requester_id == agent_id:
                result.append(n)
            elif n.visibility == "manager" and requester_depth <= 2:
                result.append(n)
        return result

    def get_all_public(self) -> str:
        lines = []
        for agent_id, notes in self._notes.items():
            public = [n for n in notes if n.visibility == "public"]
            if public:
                lines.append(f"[{agent_id}] " + "; ".join(n.content for n in public[-3:]))
        return "\n".join(lines)

    def to_dict(self, requester_id: str = "", requester_depth: int = 99) -> dict:
        return {aid: [{"content": n.content, "visibility": n.visibility, "confidence": n.confidence}
                      for n in self.read(aid, requester_id, requester_depth)]
                for aid in self._notes}

@dataclass
class BlackboardEntry:
    key: str
    value: str
    agent_id: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    ttl: float = 3600.0

    @property
    def expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl

class Blackboard:
    def __init__(self):
        self._entries: dict[str, BlackboardEntry] = {}
        self._chat_log: list[dict] = []

    def write(self, key: str, value: str, agent_id: str, confidence: float = 1.0, ttl: float = 3600.0):
        self._entries[key] = BlackboardEntry(key, value, agent_id, confidence, time.time(), ttl)
        self._chat_log.append({"agent": agent_id, "key": key, "summary": value[:120], "time": time.time()})

    def read(self, key: str) -> Optional[str]:
        entry = self._entries.get(key)
        if entry and not entry.expired:
            return entry.value
        return None

    def read_relevant(self, problem_embedding_hash: str, top_k: int = 10) -> list[dict]:
        scored = []
        for key, entry in self._entries.items():
            if entry.expired:
                continue
            sim = self._similarity(key, problem_embedding_hash)
            scored.append((sim, {"key": key, "value": entry.value[:200], "agent": entry.agent_id, "confidence": entry.confidence}))
        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]

    def _similarity(self, a: str, b: str) -> float:
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return 0.0
        return len(a_set & b_set) / len(a_set | b_set)

    def get_chat_log(self, limit: int = 20) -> list[dict]:
        return self._chat_log[-limit:]

    def clear_expired(self):
        self._entries = {k: v for k, v in self._entries.items() if not v.expired}

    def write_thought(self, agent_id: str, thought: str, tags=None, confidence=0.5):
        thought_vdb.inject(agent_id, thought, tags, confidence)
        self.write(f"thought:{agent_id}:{int(time.time()*1000)}", thought, agent_id, confidence)

    def query_thoughts(self, topic: str, top_k: int = 5) -> list[dict]:
        return thought_vdb.query(topic, top_k)

    def read_memory(self, query: str) -> list[dict]:
        return l1_memory.recall(query)

    def write_memory(self, key: str, value: str, metadata=None):
        l1_memory.store(key, value, metadata)

blackboard = Blackboard()
internal_notes = InternalNotes()
