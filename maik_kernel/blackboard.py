"""Blackboard — shared, thread-safe agent memory with public/private channels.

Kept from maik-demo v2 (audit-verified shape) with upgrades: subscription
notifications, size cap with confidence-first eviction, snapshot/restore for
replay, and JSON-API serialization.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Pattern


@dataclass
class BlackboardEntry:
    key: str
    content: Any
    agent: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    visibility: str = "public"  # "public" | "internal"

    def to_dict(self) -> dict:
        return {
            "key": self.key, "content": self.content, "agent": self.agent,
            "time": self.timestamp, "confidence": self.confidence,
            "visibility": self.visibility,
        }


class Blackboard:
    DEFAULT_CAP = 1000

    def __init__(self, cap: int = DEFAULT_CAP):
        self._data: Dict[str, List[BlackboardEntry]] = {}
        self._subs: List[tuple] = []  # (pattern, callback)
        self._lock = threading.RLock()
        self.cap = cap
        self._total = 0

    # -- core -----------------------------------------------------------
    def put(self, key: str, content: Any, agent: str,
            confidence: float = 1.0, visibility: str = "public") -> str:
        entry = BlackboardEntry(key=key, content=content, agent=agent,
                                confidence=confidence, visibility=visibility)
        with self._lock:
            self._data.setdefault(key, []).append(entry)
            self._total += 1
            self._evict_if_needed()
            subs = [cb for pat, cb in self._subs if pat.match(key)]
        for cb in subs:
            try:
                cb(entry)
            except Exception:
                pass
        return entry.key

    def get(self, key: str, visibility: str = "public") -> Optional[Any]:
        """Latest PUBLIC entry for key (agents don't see internal notes)."""
        with self._lock:
            entries = self._data.get(key, [])
        for e in reversed(entries):
            if e.visibility == visibility or visibility == "all":
                return e.content
        return None

    def get_entry(self, key: str, visibility: str = "public") -> Optional[BlackboardEntry]:
        with self._lock:
            entries = self._data.get(key, [])
        for e in reversed(entries):
            if e.visibility == visibility or visibility == "all":
                return e
        return None

    def all_keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())

    # -- internal notes -------------------------------------------------
    def note(self, key: str, content: Any, agent: str, confidence: float = 1.0) -> str:
        return self.put(key, content, agent, confidence, visibility="internal")

    # -- subscriptions --------------------------------------------------
    def subscribe(self, pattern: str, callback: Callable[[BlackboardEntry], None]) -> str:
        import re
        with self._lock:
            self._subs.append((re.compile(pattern), callback))
        return str(uuid.uuid4())[:8]

    # -- eviction -------------------------------------------------------
    def _evict_if_needed(self) -> None:
        if self._total <= self.cap:
            return
        # flatten, drop oldest lowest-confidence entries until under cap
        flat = [(e, k) for k, evs in self._data.items() for e in evs]
        flat.sort(key=lambda x: (x[0].confidence, x[0].timestamp))
        drop_n = self._total - self.cap
        for e, k in flat[:drop_n]:
            lst = self._data.get(k, [])
            if e in lst:
                lst.remove(e)
                if not lst:
                    self._data.pop(k, None)
        self._total = sum(len(v) for v in self._data.values())

    # -- snapshot / replay ----------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {k: [e.to_dict() for e in vs] for k, vs in self._data.items()}

    def restore(self, snap: dict) -> None:
        with self._lock:
            self._data.clear()
            for k, entries in snap.items():
                for d in entries:
                    d = dict(d)
                    d["timestamp"] = d.pop("time", d.get("timestamp"))
                    self._data.setdefault(k, []).append(BlackboardEntry(**d))
            self._total = sum(len(v) for v in self._data.values())

    # -- API serialization ----------------------------------------------
    def to_dict(self) -> dict:
        with self._lock:
            return {
                "entries": sum(len(v) for v in self._data.values()),
                "cap": self.cap,
                "keys": list(self._data.keys())[:100],
            }

    def __len__(self) -> int:
        with self._lock:
            return self._total
