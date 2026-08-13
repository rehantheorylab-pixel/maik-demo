"""Chat-style team threads (Phase H8).

The public notebook becomes a WhatsApp-like conversation surface:
- Any node can POST a message to a thread.
- Messages can REPLY-TO another message (quoted thread).
- Nodes can HOLD a problem: post it to a thread and siblings take turns.
- A thread can be opened for DEBATE: participants argue for/against; the
  thread resolves to CONSENSUS, CEO-VETO, or MANAGER-VETO — every veto
  must carry a written reason, and the losing side may COUNTER-ARGUE once.

This is where the org actually thinks together: ideas get proposed,
criticized, fixed, and only closed when the chain of command is satisfied.

Persisted as JSONL under MAIK_DATA_DIR/threads/{thread_id}.jsonl.
"""

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .org_chart import NodeLevel, OrgChart

STATUS_OPEN = "open"
STATUS_DEBATE = "debate"
STATUS_CONSENSUS = "consensus"
STATUS_VETOED = "vetoed"


class ThreadError(ValueError):
    pass


class Message:
    def __init__(self, thread_id: str, author_uid: str, text: str,
                 reply_to: Optional[str] = None, kind: str = "post"):
        self.id = uuid.uuid4().hex[:10]
        self.thread_id = thread_id
        self.author_uid = author_uid
        self.text = text
        self.reply_to = reply_to
        self.kind = kind  # post | reply | hold | argue | counter | close | veto
        self.ts = time.time()
        self.utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ts))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("id", "thread_id", "author_uid", "text", "reply_to",
                 "kind", "ts", "utc")}


class TeamThread:
    """One conversation thread with debate/consensus mechanics."""

    def __init__(self, thread_id: str, topic: str, owner_uid: str,
                 org: Optional[OrgChart] = None):
        self.id = thread_id
        self.topic = topic
        self.owner_uid = owner_uid
        self.org = org
        self.messages: List[Message] = []
        self.status = STATUS_OPEN
        self.participants: Dict[str, dict] = {}  # uid -> {for, against, last}
        self._lock = threading.RLock()

    # -- messaging -----------------------------------------------------
    def post(self, author_uid: str, text: str,
             reply_to: Optional[str] = None, kind: str = "post") -> Message:
        with self._lock:
            if reply_to and not any(m.id == reply_to for m in self.messages):
                raise ThreadError(f"Unknown message id {reply_to}")
            m = Message(self.id, author_uid, text, reply_to, kind)
            self.messages.append(m)
            return m

    # -- debate mechanics ---------------------------------------------
    def open_debate(self) -> None:
        with self._lock:
            if self.status != STATUS_OPEN:
                raise ThreadError("Thread not open")
            self.status = STATUS_DEBATE

    def vote(self, author_uid: str, position: str) -> None:
        """position: 'for' or 'against'."""
        if position not in ("for", "against"):
            raise ThreadError("position must be for/against")
        with self._lock:
            p = self.participants.setdefault(author_uid, {"for": 0, "against": 0})
            p[position] += 1

    def close_consensus(self, by_uid: str) -> Message:
        with self._lock:
            if self.status == STATUS_CONSENSUS:
                raise ThreadError("already closed by consensus")
            if not self._may_close(by_uid):
                raise ThreadError(f"{by_uid} cannot close this thread")
            self.status = STATUS_CONSENSUS
            return self.post(by_uid, "THREAD CLOSED: consensus reached.",
                             kind="close")

    def veto(self, by_uid: str, reason: str) -> Message:
        """CEO/manager veto — must state why, and the proposer may
        counter-argue once."""
        if not (len(reason or "") >= 10):
            raise ThreadError("A veto must explain why (>= 10 chars)")
        with self._lock:
            if not self._may_veto(by_uid):
                raise ThreadError(f"{by_uid} cannot veto")
            self.status = STATUS_VETOED
            return self.post(by_uid, f"VETO: {reason}", kind="veto")

    def counter_argue(self, author_uid: str, text: str) -> Message:
        with self._lock:
            if self.status != STATUS_VETOED:
                raise ThreadError("No active veto to counter")
            if any(m.kind == "counter" and m.author_uid == author_uid
                   for m in self.messages):
                raise ThreadError(f"{author_uid} already used their counter")
            m = self.post(author_uid, text, kind="counter")
            # one counter re-opens the debate
            self.status = STATUS_DEBATE
            return m

    # -- visibility ----------------------------------------------------
    def _may_close(self, uid: str) -> bool:
        if self.org is None:
            return uid == self.owner_uid
        node = self.org.node(uid)
        return node is not None and node.level in (NodeLevel.CEO,
                                                   NodeLevel.MANAGER)

    def _may_veto(self, uid: str) -> bool:
        if self.org is None:
            return False
        node = self.org.node(uid)
        return node is not None and node.level in (NodeLevel.CEO,
                                                   NodeLevel.MANAGER)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "topic": self.topic, "owner_uid": self.owner_uid,
            "status": self.status,
            "messages": [m.to_dict() for m in self.messages],
        }


class ThreadHub:
    """Org-wide thread manager with persistence."""

    def __init__(self, org: Optional[OrgChart] = None,
                 base: Optional[Path] = None):
        self.org = org
        self.base = Path(base) if base else Path(
            os.environ.get("MAIK_DATA_DIR", ".")) / "threads"
        self.base.mkdir(parents=True, exist_ok=True)
        self._threads: Dict[str, TeamThread] = {}
        self._lock = threading.RLock()
        self._load_all()

    # -- persistence (threads survive across CLI invocations) ----------
    def _path(self, thread_id: str) -> Path:
        return self.base / f"{thread_id}.jsonl"

    def _load_all(self) -> None:
        """Load every persisted thread from JSONL files (process-safe)."""
        with self._lock:
            for p in sorted(self.base.glob("*.jsonl")):
                tid = p.stem
                if tid in self._threads:
                    continue
                t = TeamThread(tid, topic="", owner_uid="", org=self.org)
                for line in p.read_text().strip().splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if not t.topic:
                        t.topic = d.get("topic", "")
                    if not t.owner_uid:
                        t.owner_uid = d.get("owner_uid", "")
                    if "msg" in d:
                        t.messages.append(Message(
                            tid, d["msg"]["author_uid"], d["msg"]["text"],
                            reply_to=d["msg"].get("reply_to"),
                            kind=d["msg"].get("kind", "post")))
                # status follows the chronological order of closing events
                kinds = [m.kind for m in t.messages]
                last_close = None
                for i, k in enumerate(kinds):
                    if k in ("veto", "close", "counter"):
                        last_close = k
                if last_close == "veto":
                    t.status = STATUS_VETOED
                elif last_close == "close":
                    t.status = STATUS_CONSENSUS
                elif last_close == "counter":
                    t.status = STATUS_DEBATE
                else:
                    t.status = STATUS_DEBATE if "argue" in kinds else STATUS_OPEN
                self._threads[tid] = t

    def _persist(self, t: TeamThread) -> None:
        """Write the full thread snapshot atomically."""
        lines = [json.dumps({"topic": t.topic, "owner_uid": t.owner_uid,
                             "status": t.status, "msg": m.to_dict()})
                 for m in t.messages]
        tmp = self._path(t.id).with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + "\n")
        tmp.replace(self._path(t.id))

    def create(self, topic: str, owner_uid: str) -> TeamThread:
        t = TeamThread(str(uuid.uuid4().hex[:10]), topic, owner_uid, self.org)
        with self._lock:
            self._threads[t.id] = t
        self._persist(t)
        return t

    def get(self, thread_id: str) -> Optional[TeamThread]:
        if thread_id not in self._threads:
            self._load_all()  # another process may have created it
        return self._threads.get(thread_id)

    def all_threads(self) -> List[TeamThread]:
        return list(self._threads.values())

    def hold(self, owner_uid: str, problem: str) -> TeamThread:
        """Hold a problem open for the team to think about together."""
        t = self.create(f"HOLD: {problem[:80]}", owner_uid)
        t.post(owner_uid, problem, kind="hold")
        return t

    def open_debate(self, thread_id: str) -> None:
        t = self.get(thread_id)
        if t is None:
            raise ThreadError("unknown thread")
        t.open_debate()
        self._persist(t)

    def summary(self) -> dict:
        return {
            "threads": len(self._threads),
            "by_status": {s: sum(1 for t in self._threads.values()
                                 if t.status == s)
                          for s in (STATUS_OPEN, STATUS_DEBATE,
                                    STATUS_CONSENSUS, STATUS_VETOED)},
        }
