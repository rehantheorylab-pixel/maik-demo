import time
import heapq
import uuid
from dataclasses import dataclass, field
from typing import Optional

@dataclass(order=True)
class Task:
    priority_score: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent_type: str = ""
    description: str = ""
    estimated_cost: float = 0.0
    urgency: float = 0.5
    dependencies: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"

class CostAwareScheduler:
    def __init__(self):
        self._queue: list[Task] = []
        self._running: dict[str, Task] = {}
        self._completed: list[dict] = []
        self._agent_availability: dict[str, int] = {}
        self._budget_spent = 0.0

    def register_agent(self, agent_type: str, max_concurrent: int = 3):
        self._agent_availability[agent_type] = max_concurrent

    def enqueue(self, description: str, agent_type: str = "general",
                estimated_cost: float = 100.0, urgency: float = 0.5,
                dependencies: Optional[list[str]] = None) -> str:
        score = self._compute_priority(urgency, estimated_cost, agent_type)
        task = Task(
            priority_score=-score,
            agent_type=agent_type, description=description,
            estimated_cost=estimated_cost, urgency=urgency,
            dependencies=dependencies or [],
        )
        heapq.heappush(self._queue, task)
        return task.id

    def _compute_priority(self, urgency: float, cost: float, agent_type: str) -> float:
        base = urgency * 10.0
        cost_penalty = cost / 1000.0
        avail = self._agent_availability.get(agent_type, 1)
        availability_bonus = avail * 0.5
        return base - cost_penalty + availability_bonus

    def dequeue(self, agent_type: str = "") -> Optional[Task]:
        candidates = []
        while self._queue:
            task = heapq.heappop(self._queue)
            running_count = sum(1 for t in self._running.values() if t.agent_type == task.agent_type)
            avail = self._agent_availability.get(task.agent_type, 1)
            if running_count < avail:
                if agent_type and task.agent_type != agent_type:
                    candidates.append(task)
                    continue
                if any(dep in self._running for dep in task.dependencies):
                    task.priority_score -= 5.0
                    heapq.heappush(self._queue, task)
                    continue
                task.status = "running"
                self._running[task.id] = task
                self._budget_spent += task.estimated_cost
                for c in candidates:
                    heapq.heappush(self._queue, c)
                return task
            candidates.append(task)
        for c in candidates:
            heapq.heappush(self._queue, c)
        return None

    def complete(self, task_id: str, outcome: str = "success", tokens_used: int = 0):
        task = self._running.pop(task_id, None)
        if task:
            entry = {
                "id": task.id, "agent_type": task.agent_type,
                "description": task.description[:80], "outcome": outcome,
                "tokens_used": tokens_used, "cost": task.estimated_cost,
                "duration": time.time() - task.created_at,
            }
            self._completed.append(entry)

    def fail(self, task_id: str, reason: str = ""):
        task = self._running.pop(task_id, None)
        if task:
            self._completed.append({
                "id": task.id, "agent_type": task.agent_type,
                "description": task.description[:80], "outcome": "failed",
                "reason": reason, "cost": task.estimated_cost,
            })

    def stats(self) -> dict:
        return {
            "queue_size": len(self._queue),
            "running": len(self._running),
            "completed": len(self._completed),
            "budget_spent": self._budget_spent,
            "agents": self._agent_availability,
        }

    def next_up(self, n: int = 5) -> list[dict]:
        return [{"id": t.id, "desc": t.description[:60], "agent": t.agent_type, "urgency": t.urgency}
                for t in sorted(self._queue, key=lambda t: t.priority_score)[:n]]

scheduler = CostAwareScheduler()
scheduler.register_agent("route", 3)
scheduler.register_agent("execute", 5)
scheduler.register_agent("learn", 2)
scheduler.register_agent("decompose", 4)
scheduler.register_agent("synthesize", 2)
