import time
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class MetaPrompt:
    id: str
    content: str
    version: int = 1
    effectiveness: float = 0.5
    created_at: float = field(default_factory=time.time)

class MetaAgent:
    def __init__(self, agent_id: str = "meta-controller"):
        self.id = agent_id
        self._sub_agents: dict[str, dict] = {}
        self._prompts: dict[str, MetaPrompt] = {}
        self._decisions: list[dict] = []
        self._critiques: list[dict] = []

    def register_sub_agent(self, agent_id: str, role: str, capabilities: Optional[list[str]] = None):
        self._sub_agents[agent_id] = {
            "role": role, "capabilities": capabilities or [],
            "status": "idle", "tasks_completed": 0, "avg_confidence": 0.5,
        }

    def delegate(self, sub_agent_id: str, task: str, context: Optional[dict] = None) -> str:
        decision_id = hashlib.md5(f"{time.time()}:{sub_agent_id}:{task}".encode()).hexdigest()[:8]
        decision = {
            "id": decision_id, "sub_agent": sub_agent_id,
            "task": task[:80], "context": context or {},
            "timestamp": time.time(), "status": "dispatched",
        }
        self._decisions.append(decision)
        if sub_agent_id in self._sub_agents:
            self._sub_agents[sub_agent_id]["status"] = "busy"
        return decision_id

    def complete_task(self, sub_agent_id: str, outcome: str = "success", confidence: float = 0.7):
        if sub_agent_id in self._sub_agents:
            agent = self._sub_agents[sub_agent_id]
            agent["status"] = "idle"
            agent["tasks_completed"] += 1
            agent["avg_confidence"] = (agent["avg_confidence"] * (agent["tasks_completed"] - 1) + confidence) / agent["tasks_completed"]

    def add_prompt(self, name: str, content: str) -> str:
        prompt_id = hashlib.md5(name.encode()).hexdigest()[:8]
        self._prompts[name] = MetaPrompt(id=prompt_id, content=content)
        return prompt_id

    def revise_prompt(self, name: str, new_content: str):
        if name in self._prompts:
            p = self._prompts[name]
            p.content = new_content
            p.version += 1

    def get_prompt(self, name: str) -> Optional[str]:
        p = self._prompts.get(name)
        return p.content if p else None

    def write_critique(self, decision_id: str, verdict: str, recommendation: str):
        self._critiques.append({
            "decision_id": decision_id, "verdict": verdict,
            "recommendation": recommendation, "timestamp": time.time(),
        })

    def stats(self) -> dict:
        return {
            "sub_agents": len(self._sub_agents),
            "total_decisions": len(self._decisions),
            "total_critiques": len(self._critiques),
            "prompts": len(self._prompts),
            "agents": {aid: {"role": a["role"], "status": a["status"], "tasks": a["tasks_completed"]}
                       for aid, a in self._sub_agents.items()},
        }

class StateMachine:
    def __init__(self):
        self._states: dict[str, str] = {}
        self._transitions: list[dict] = []

    def set_state(self, agent_id: str, state: str):
        prev = self._states.get(agent_id, "init")
        self._states[agent_id] = state
        self._transitions.append({
            "agent": agent_id, "from": prev, "to": state, "time": time.time(),
        })

    def get_state(self, agent_id: str) -> str:
        return self._states.get(agent_id, "init")

    def transitions_for(self, agent_id: str) -> list[dict]:
        return [t for t in self._transitions if t["agent"] == agent_id]

    def all_states(self) -> dict:
        return dict(self._states)

meta_agent = MetaAgent()
state_machine = StateMachine()
