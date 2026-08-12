"""Session Compaction — loguru-style rotation + TextRank summarization + SQLite FTS5 search."""
from __future__ import annotations
import time, json, os, re, hashlib, gzip, shutil, threading, sqlite3, textwrap
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import Counter

SESSION_DIR = Path("memory/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
COMPACT_DIR = Path("memory/compacted")
COMPACT_DIR.mkdir(parents=True, exist_ok=True)
_DB = COMPACT_DIR / "archive.db"


def _ensure_db():
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, label TEXT, file_path TEXT, summary TEXT,
        message_count INTEGER, total_bytes INTEGER, compressed_ratio REAL,
        timestamp REAL, tags TEXT
    )""")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(
        id, label, summary, content
    )""")
    conn.commit()
    return conn


@dataclass
class CompactedSession:
    id: str
    label: str
    file_path: str
    summary: str
    message_count: int
    total_bytes: int
    compressed_ratio: float
    timestamp: float
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SessionArchiver:
    """Rotating archiver with gzip compression and FTS5 search."""

    MAX_ROTATION_BYTES = 50 * 1024 * 1024  # 50 MB per file

    def __init__(self):
        self._conn = _ensure_db()
        self._lock = threading.Lock()

    def archive(self, session_id: str, label: str, messages: list[dict], summary: str,
                tags: Optional[list[str]] = None) -> CompactedSession:
        with self._lock:
            timestamp = time.time()
            content_md = self._render_markdown(session_id, label, messages, summary)
            raw_bytes = len(json.dumps(messages).encode())
            compressed = gzip.compress(content_md.encode())
            ratio = raw_bytes / max(len(compressed), 1)
            file_name = f"session_{session_id}_{int(timestamp)}.md.gz"
            file_path = COMPACT_DIR / file_name
            file_path.write_bytes(compressed)
            cs = CompactedSession(
                id=session_id, label=label, file_path=str(file_path),
                summary=summary, message_count=len(messages),
                total_bytes=len(compressed), compressed_ratio=ratio,
                timestamp=timestamp, tags=tags or [],
            )
            self._upsert_db(cs)
            self._upsert_fts(session_id, label, summary, content_md)
            self._rotate_if_needed()
            return cs

    def _render_markdown(self, sid: str, label: str, msgs: list[dict], summary: str) -> str:
        lines = [
            f"# Session: {label} ({sid})",
            f"Archived: {time.ctime()}",
            f"Messages: {len(msgs)}",
            f"Summary: {summary}",
            "",
        ]
        for msg in msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"## [{role.upper()}]")
            lines.append(str(content))
            lines.append("")
        return "\n".join(lines)

    def _upsert_db(self, cs: CompactedSession):
        self._conn.execute("""INSERT OR REPLACE INTO sessions
            (id, label, file_path, summary, message_count, total_bytes, compressed_ratio, timestamp, tags)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (cs.id, cs.label, cs.file_path, cs.summary, cs.message_count,
             cs.total_bytes, cs.compressed_ratio, cs.timestamp, json.dumps(cs.tags)))
        self._conn.commit()

    def _upsert_fts(self, sid: str, label: str, summary: str, content: str):
        self._conn.execute("INSERT OR REPLACE INTO session_fts(id, label, summary, content) VALUES (?,?,?,?)",
                           (sid, label, summary, content[:50000]))
        self._conn.commit()

    def _rotate_if_needed(self):
        total = COMPACT_DIR.stat().st_size if COMPACT_DIR.exists() else 0
        if total > self.MAX_ROTATION_BYTES * 2:
            old = sorted(COMPACT_DIR.glob("*.md.gz"), key=lambda p: p.stat().st_mtime)
            while total > self.MAX_ROTATION_BYTES and len(old) > 1:
                removed = old.pop(0)
                total -= removed.stat().st_size
                removed.unlink(missing_ok=True)

    def get(self, session_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            cols = [d[0] for d in self._conn.execute("PRAGMA table_info(sessions)").fetchall()]
            return dict(zip(cols, row))
        return None

    def get_all(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, label, file_path, summary, message_count, timestamp FROM sessions ORDER BY timestamp DESC").fetchall()
        return [{"id": r[0], "label": r[1], "file": r[2], "summary": (r[3] or "")[:80],
                 "messages": r[4], "timestamp": r[5]} for r in rows]

    def search_content(self, query: str, session_id: str = "", limit: int = 10) -> list[dict]:
        try:
            q = query.replace("'", "''")
            sql = "SELECT id, label, snippet(session_fts, -1, '<<<', '>>>', '...', 64) AS ctx FROM session_fts WHERE session_fts MATCH ?"
            params = [f'"{q}"']
            if session_id:
                sql += " AND id=?"
                params.append(session_id)
            sql += f" LIMIT {limit}"
            rows = self._conn.execute(sql, params).fetchall()
            return [{"session": r[0], "label": r[1], "context": r[2]} for r in rows]
        except sqlite3.OperationalError:
            return self._fallback_search(query, session_id, limit)

    def _fallback_search(self, query: str, session_id: str, limit: int) -> list[dict]:
        q = query.lower()
        hits = []
        rows = self._conn.execute("SELECT id, label, file_path FROM sessions").fetchall()
        for sid, label, fp in rows:
            if session_id and sid != session_id:
                continue
            path = Path(fp)
            if not path.exists():
                continue
            try:
                raw = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
            except Exception:
                raw = path.read_text(encoding="utf-8", errors="replace")
            if q in raw.lower():
                idx = raw.lower().find(q)
                start = max(0, idx - 100)
                end = min(len(raw), idx + 100)
                ctx = raw[start:end].replace("\n", " ")
                hits.append({"session": sid, "context": f"...{ctx}..."})
        return hits[:limit]

    def stats(self) -> dict:
        row = self._conn.execute("SELECT COUNT(*), COALESCE(SUM(message_count),0), COALESCE(SUM(total_bytes),0) FROM sessions").fetchone()
        return {
            "compacted_sessions": row[0],
            "total_messages": row[1],
            "total_bytes": row[2],
            "storage_path": str(COMPACT_DIR),
        }

    def delete(self, session_id: str):
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            self._conn.execute("DELETE FROM session_fts WHERE id=?", (session_id,))
            self._conn.commit()


session_archiver = SessionArchiver()


# ── TextRank summarizer (no ML deps) ──────────────────────────────

class SummaryGenerator:
    """Extractive summarization using TextRank on sentence graphs."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    def generate(self, messages: list[dict], max_chars: int = 600) -> str:
        if not messages:
            return "No messages to summarize."
        content = "\n".join(str(m.get("content", "")) for m in messages[-150:])
        key = hashlib.md5(content.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        sentences = self._split_sentences(content)
        if len(sentences) <= 3:
            result = " ".join(sentences)[:max_chars]
            self._cache[key] = result
            return result
        ranked = self._textrank(sentences)
        top = [s for s, _ in ranked[:5]]
        result = " ".join(top)[:max_chars]
        self._cache[key] = result
        return result

    def generate_structured(self, messages: list[dict]) -> dict:
        s = self.generate(messages)
        return {
            "summary": s,
            "message_count": len(messages),
            "has_user_input": any(m.get("role") == "user" for m in messages),
            "last_user": next((str(m.get("content", ""))[:200] for m in reversed(messages) if m.get("role") == "user"), ""),
            "participants": list(set(str(m.get("role", "")) for m in messages)),
        }

    def _split_sentences(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        raw = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [s.strip() for s in raw if len(s.strip()) > 20][:100]

    def _textrank(self, sentences: list[str], top_n: int = 5) -> list[tuple[str, float]]:
        n = len(sentences)
        sim = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                s = self._jaccard(sentences[i], sentences[j])
                sim[i][j] = sim[j][i] = s
        scores = [1.0 / n] * n
        for _ in range(20):
            new = [0.0] * n
            for i in range(n):
                total = sum(sim[i][j] for j in range(n) if j != i)
                if total == 0:
                    new[i] = scores[i]
                else:
                    for j in range(n):
                        if j != i:
                            new[i] += sim[i][j] / total * scores[j]
            scores = new
        ranked = sorted(zip(sentences, scores), key=lambda x: -x[1])
        return ranked[:top_n]

    def _jaccard(self, a: str, b: str) -> float:
        wa = set(re.findall(r"\w+", a.lower()))
        wb = set(re.findall(r"\w+", b.lower()))
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)


summary_generator = SummaryGenerator()


# ── Agent context builder ──────────────────────────────────────────

class AgentContextBuilder:
    def build_context(self, session_id: str, max_summary_len: int = 800) -> dict:
        details = session_archiver.get(session_id)
        if not details:
            return {"error": f"Session {session_id} not found"}
        return {
            "session_id": session_id,
            "label": details["label"],
            "summary": details["summary"][:max_summary_len],
            "archive_file": details["file_path"],
            "total_messages": details["message_count"],
            "search_hint": "Use session_archiver.search_content(query, session_id) for details.",
        }

    def build_reduced_context(self, session_ids: list[str], max_len: int = 400) -> list[dict]:
        return [self.build_context(sid, max_len) for sid in session_ids]

    def agent_prompt(self, session_ids: list[str]) -> str:
        ctxs = self.build_reduced_context(session_ids)
        parts = ["[PREVIOUS SESSION CONTEXT]"]
        for ctx in ctxs:
            if "error" in ctx:
                continue
            parts.append(f"Session: {ctx['session_id']} ({ctx['label']})")
            parts.append(f"Summary: {ctx['summary']}")
            parts.append(f"Archive: {ctx['archive_file']}")
            parts.append("")
        parts.append("[END CONTEXT]")
        return "\n".join(parts)


agent_context_builder = AgentContextBuilder()


# ── Auto-compaction manager ────────────────────────────────────────

class CompactionManager:
    def __init__(self, max_before_compact: int = 50):
        self._max = max_before_compact
        self._pending: list[dict] = []
        self._current_session_id: Optional[str] = None
        self._timer: Optional[threading.Timer] = None

    def start_session(self, session_id: str):
        self._current_session_id = session_id
        self._pending = []

    def add_message(self, role: str, content: str, metadata: Optional[dict] = None):
        self._pending.append({
            "role": role, "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })

    def should_compact(self) -> bool:
        return len(self._pending) >= self._max

    def compact(self, label: str = "") -> Optional[dict]:
        if not self.should_compact() or not self._current_session_id:
            return None
        summary = summary_generator.generate(self._pending)
        archived = session_archiver.archive(
            self._current_session_id, label or f"Session {self._current_session_id}",
            self._pending, summary
        )
        carry = self._pending[-5:]
        self._pending = carry
        for msg in self._pending:
            msg["from_archive"] = True
            msg["archive_id"] = self._current_session_id
        return {
            "session_id": self._current_session_id,
            "archived": archived.message_count,
            "summary": summary,
            "file": archived.file_path,
            "carry_over": len(carry),
        }

    def force_compact_all(self, label: str = "") -> Optional[dict]:
        if not self._pending or not self._current_session_id:
            return None
        saved = list(self._pending)
        self._pending = []
        summary = summary_generator.generate(saved)
        archived = session_archiver.archive(
            self._current_session_id, label or f"Session {self._current_session_id}",
            saved, summary
        )
        return {
            "session_id": self._current_session_id,
            "archived": archived.message_count,
            "summary": summary,
            "file": archived.file_path,
        }

    def get_agent_context_prompt(self) -> str:
        if not self._current_session_id:
            return ""
        return agent_context_builder.agent_prompt([self._current_session_id])

    def stats(self) -> dict:
        return {
            "pending": len(self._pending),
            "max_before_compact": self._max,
            "current_session": self._current_session_id or "",
            "archiver": session_archiver.stats(),
        }


compaction_manager = CompactionManager(max_before_compact=50)
