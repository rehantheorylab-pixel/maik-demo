import time, hashlib, uuid
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Session:
    id: str
    label: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    task_count: int = 0
    success_count: int = 0

class SessionManager:
    def __init__(self):
        self._sessions: list[Session] = []

    def start(self, label: str = "") -> str:
        sid = hashlib.md5(f"{time.time()}:{label}".encode()).hexdigest()[:12]
        self._sessions.append(Session(id=sid, label=label or f"Session {len(self._sessions)+1}"))
        return sid

    def end(self, session_id: str):
        for s in self._sessions:
            if s.id == session_id:
                s.ended_at = time.time()
                break

    def record_task(self, session_id: str, success: bool):
        for s in self._sessions:
            if s.id == session_id:
                s.task_count += 1
                if success: s.success_count += 1
                break

    def active(self) -> Optional[dict]:
        for s in self._sessions:
            if s.ended_at is None:
                return {"id": s.id, "label": s.label, "started": time.strftime("%H:%M:%S", time.localtime(s.started_at)),
                        "tasks": s.task_count, "success": s.success_count,
                        "rate": f"{s.success_count/max(s.task_count,1):.0%}"}
        return None

    def list_sessions(self) -> list[dict]:
        return [{"id": s.id, "label": s.label, "started": time.strftime("%H:%M:%S", time.localtime(s.started_at)),
                 "ended": time.strftime("%H:%M:%S", time.localtime(s.ended_at)) if s.ended_at else "active",
                 "tasks": s.task_count, "success_rate": f"{s.success_count/max(s.task_count,1):.0%}"}
                for s in self._sessions]

    def stats(self) -> dict:
        total = len(self._sessions)
        active_count = sum(1 for s in self._sessions if s.ended_at is None)
        total_tasks = sum(s.task_count for s in self._sessions)
        total_success = sum(s.success_count for s in self._sessions)
        return {"total": total, "active": active_count, "total_tasks": total_tasks,
                "avg_success": f"{total_success/max(total_tasks,1):.0%}"}

session_manager = SessionManager()
