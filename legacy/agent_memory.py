"""Agent memory — persistent session memory with search and recall.

Absorbs:
  - Claude Code: session context, task memory
  - Custom: keyword-indexed memory store, session management
"""

import os, json, time, re
from pathlib import Path
from datetime import datetime


MEMORY_DIR = Path.home() / ".maik" / "memories"
SESSION_DIR = Path.home() / ".maik" / "sessions"


def _ensure_dir():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _mem_path(key):
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', key)
    return MEMORY_DIR / f"{safe}.json"


def _session_path(session_id):
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)
    return SESSION_DIR / f"{safe}.json"


class AgentMemory:
    """Persistent agent memory with keyword search and session management."""

    def __init__(self):
        _ensure_dir()
        self._cache = {}
        self._session_buf = {}

    # --- CRUD ---

    def store(self, key, data, metadata=None):
        path = _mem_path(key)
        entry = {
            "key": key,
            "data": data,
            "metadata": metadata or {},
            "created": time.time(),
            "updated": time.time(),
        }
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing["data"] = data
            existing["metadata"] = metadata or existing.get("metadata", {})
            existing["updated"] = time.time()
            entry = existing
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2)
        self._cache[key] = entry
        return {"stored": key, "size": len(json.dumps(entry))}

    def recall(self, key):
        path = _mem_path(key)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def search(self, query, top_k=10):
        results = []
        q = query.lower()
        for path in MEMORY_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                text = json.dumps(entry).lower()
                score = self._score(text, q)
                if score > 0:
                    results.append((score, entry))
            except (json.JSONDecodeError, OSError):
                continue
        results.sort(key=lambda x: -x[0])
        return [r[1] for r in results[:top_k]]

    def _score(self, text, query):
        words = query.split()
        matches = sum(1 for w in words if w in text)
        return matches / len(words) if words else 0

    def forget(self, key):
        path = _mem_path(key)
        if path.exists():
            path.unlink()
            self._cache.pop(key, None)
            return True
        return False

    def list_keys(self, prefix=None):
        keys = []
        for path in MEMORY_DIR.glob("*.json"):
            key = path.stem
            if prefix and not key.startswith(prefix):
                continue
            keys.append(key)
        return sorted(keys)

    def stats(self):
        keys = self.list_keys()
        total_size = 0
        for k in keys:
            path = _mem_path(k)
            if path.exists():
                total_size += path.stat().st_size
        return {
            "total_entries": len(keys),
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 1),
            "keys": keys[:20],
            "has_more": len(keys) > 20,
        }

    # --- Session (disk-persisted) ---

    def session_start(self, session_id=None):
        if session_id is None:
            session_id = f"session_{int(time.time())}"
        path = _session_path(session_id)
        if not path.exists():
            data = {"session_id": session_id, "events": [], "created": time.time()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        self._session_buf[session_id] = True
        return session_id

    def session_log(self, session_id, event_type, content):
        path = _session_path(session_id)
        if not path.exists():
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("events", []).append({
            "type": event_type,
            "content": content,
            "timestamp": time.time(),
        })
        data["updated"] = time.time()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True

    def session_save(self, session_id):
        path = _session_path(session_id)
        return path.exists()

    def session_load(self, session_id):
        path = _session_path(session_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def session_list(self):
        sessions = []
        for path in sorted(SESSION_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                sessions.append({
                    "session_id": s["session_id"],
                    "events": len(s.get("events", [])),
                    "created": s.get("created", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return sessions


agent_memory = AgentMemory()
