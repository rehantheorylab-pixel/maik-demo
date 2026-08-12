import time
import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

from config import WORKFLOW_CHAINS, WorkflowStep

@dataclass
class MetaPrompt:
    id: str
    content: str
    version: int = 1
    effectiveness: float = 0.5
    created_at: float = field(default_factory=time.time)

PROMPT_TEMPLATES = {
    "coding": "You are an expert programmer. Write production-quality code for: {task}",
    "thinking": "You are a logical reasoning agent. Think step by step about: {task}",
    "error_finding": "You are a strict code reviewer. Find ALL errors, bugs, and issues in this:\n{previous_output}",
    "confirming": "You are a quality assurance agent. Confirm if the work passes all checks:\n{previous_output}",
    "idea_generating": "You are a creative innovator. Generate novel ideas and improvements for:\n{previous_output}",
    "error_fixing": "You are a fixer agent. Fix ALL errors found:\n{previous_output}",
    "research": "You are a deep researcher. Thoroughly investigate: {task}",
    "planning": "You are a strategic planner. Create a detailed plan for: {task}",
    "synthesizing": "You are a synthesis agent. Merge all findings into a cohesive result:\n{previous_output}",
    "verifying": "You are a verification agent. Fact-check and verify all claims:\n{previous_output}",
    "polishing": "You are a perfectionist. Polish and refine to final quality:\n{previous_output}",
}

class PromptSelector:
    def __init__(self):
        self._custom_prompts: dict[str, str] = {}

    def select_prompt(self, role: str, task: str = "", previous_output: str = "") -> str:
        template = self._custom_prompts.get(role) or PROMPT_TEMPLATES.get(role, "You are a helpful AI. Handle: {task}")
        return template.format(task=task, previous_output=previous_output[:2000])

    def set_custom_prompt(self, role: str, prompt: str):
        self._custom_prompts[role] = prompt

    def list_roles(self) -> list[str]:
        return list(PROMPT_TEMPLATES.keys())

    def list_custom(self) -> dict:
        return dict(self._custom_prompts)

    def reset_role(self, role: str):
        self._custom_prompts.pop(role, None)

class WorkflowEngine:
    def __init__(self):
        self._active_runs: dict[str, dict] = {}

    def run_chain(self, chain_id: str, task: str, chain_config: dict = None) -> str:
        run_id = hashlib.md5(f"{chain_id}:{time.time()}".encode()).hexdigest()[:12]
        if chain_config is None:
            chain_config = WORKFLOW_CHAINS.get(chain_id, {})
        self._active_runs[run_id] = {
            "chain_id": chain_id,
            "chain_name": chain_config.get("name", chain_id),
            "task": task,
            "steps": [],
            "current_step": 0,
            "status": "running",
            "started_at": time.time(),
        }
        return run_id

    def advance_step(self, run_id: str, step_output: str = "") -> Optional[dict]:
        run = self._active_runs.get(run_id)
        if not run or run["status"] != "running":
            return None
        chain = WORKFLOW_CHAINS.get(run["chain_id"])
        if not chain:
            run["status"] = "error"
            return None
        steps = chain["steps"]
        idx = run["current_step"]
        if idx >= len(steps):
            run["status"] = "completed"
            run["completed_at"] = time.time()
            return None
        step = steps[idx]
        entry = {
            "step_id": step.id,
            "role": step.role,
            "prompt": step.system_prompt,
            "output": step_output,
            "status": "pending" if not step_output else "completed",
        }
        run["steps"].append(entry)
        if step_output:
            run["current_step"] = idx + 1
            if run["current_step"] >= len(steps):
                run["status"] = "completed"
                run["completed_at"] = time.time()
                return None
            next_step = steps[run["current_step"]]
            return {"next_role": next_step.role, "next_prompt": next_step.system_prompt, "previous_output": step_output}
        return {"next_role": step.role, "next_prompt": step.system_prompt, "previous_output": ""}

    def run_all_simulated(self, chain_id: str, task: str) -> dict:
        run_id = self.run_chain(chain_id, task)
        chain = WORKFLOW_CHAINS.get(chain_id, {"steps": [], "name": chain_id})
        outputs = []
        previous = task
        for i, step in enumerate(chain.get("steps", [])):
            prompt = step.system_prompt.replace("{task}", task)[:100]
            simulated = f"[{step.role.upper()}] Analyzed: {previous[:60]}..."
            outputs.append(f"Step {i+1} ({step.role}): {simulated}")
            previous = simulated
            self.advance_step(run_id, simulated)
        run = self._active_runs.get(run_id, {})
        return {
            "run_id": run_id,
            "chain": chain.get("name", chain_id),
            "steps": run.get("steps", []),
            "outputs": outputs,
            "status": "completed",
            "duration_s": round(time.time() - run.get("started_at", time.time()), 2),
        }

    def run_status(self, run_id: str) -> Optional[dict]:
        return self._active_runs.get(run_id)

    def list_runs(self) -> list[dict]:
        return [{"id": rid, "chain": r["chain_name"], "task": r["task"][:50],
                 "step": r["current_step"], "status": r["status"]}
                for rid, r in self._active_runs.items()]

prompt_selector = PromptSelector()
workflow_engine = WorkflowEngine()

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
