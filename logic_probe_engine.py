import time, hashlib, random
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ProbedThought:
    id: str
    thought: str
    agent: str
    category: str
    severity: float
    flagged: bool = False
    resolved: bool = False
    created_at: float = field(default_factory=time.time)

class LogicProbe:
    def __init__(self):
        self._thoughts: list[ProbedThought] = []
        self._contradictions: list[dict] = []

    def probe(self, thought: str, agent: str, category: str = "general", severity: float = 0.3) -> ProbedThought:
        pid = hashlib.md5(f"{thought}:{time.time()}".encode()).hexdigest()[:8]
        flagged = severity > 0.6 or "contradict" in thought.lower() or "dangerous" in thought.lower()
        pt = ProbedThought(pid, thought, agent, category, severity, flagged)
        self._thoughts.append(pt)
        if flagged:
            self._contradictions.append({
                "thought_id": pid, "thought": thought[:80], "agent": agent,
                "severity": severity, "time": time.time(),
            })
        return pt

    def resolve(self, thought_id: str):
        for t in self._thoughts:
            if t.id == thought_id:
                t.resolved = True
                t.flagged = False
                break

    def flagged_thoughts(self, min_severity: float = 0.0) -> list[dict]:
        return [{"id": t.id, "thought": t.thought[:80], "agent": t.agent,
                 "category": t.category, "severity": t.severity, "resolved": t.resolved}
                for t in self._thoughts if t.flagged and t.severity >= min_severity]

    def contradictions(self) -> list[dict]:
        return self._contradictions

    def stats(self) -> dict:
        total = len(self._thoughts)
        flagged = sum(1 for t in self._thoughts if t.flagged)
        resolved = sum(1 for t in self._thoughts if t.resolved)
        cats = {}
        for t in self._thoughts:
            cats[t.category] = cats.get(t.category, 0) + 1
        return {"total": total, "flagged": flagged, "resolved": resolved, "categories": cats}

    def all_thoughts(self) -> list[dict]:
        return [{"id": t.id, "thought": t.thought[:80], "agent": t.agent,
                 "category": t.category, "severity": t.severity,
                 "flagged": t.flagged, "resolved": t.resolved}
                for t in self._thoughts]

logic_probe = LogicProbe()
