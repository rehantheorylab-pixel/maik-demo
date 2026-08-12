import time, hashlib, json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SheriffRule:
    id: str
    name: str
    description: str
    action: str
    enabled: bool = True
    priority: int = 5
    created_at: float = field(default_factory=time.time)

DEFAULT_RULES = [
    SheriffRule("rule-1", "Safety First", "Always check stop light before executing", "check_stop_light", True, 1),
    SheriffRule("rule-2", "Budget Check", "Verify sufficient budget before dispatch", "check_budget", True, 2),
    SheriffRule("rule-3", "Confidence Gate", "Minimum confidence threshold for execution", "check_confidence", True, 3),
    SheriffRule("rule-4", "Circuit Breaker", "Respect circuit breaker state", "check_circuit", True, 4),
    SheriffRule("rule-5", "Kill Switch", "Honor kill file detection", "check_kill", True, 5),
    SheriffRule("rule-6", "Purity Check", "Run purity test on outputs", "check_purity", True, 6),
    SheriffRule("rule-7", "Max Depth", "Respect max agent tree depth", "check_depth", True, 7),
]

class Sheriff:
    def __init__(self):
        self._rules: dict[str, SheriffRule] = {r.id: r for r in DEFAULT_RULES}
        self._enforcement_log: list[dict] = []

    def add_rule(self, name: str, description: str, action: str, priority: int = 5) -> str:
        rid = f"rule-{len(self._rules)+1}"
        self._rules[rid] = SheriffRule(rid, name, description, action, True, priority)
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def toggle(self, rule_id: str) -> Optional[bool]:
        r = self._rules.get(rule_id)
        if r:
            r.enabled = not r.enabled
            return r.enabled
        return None

    def enforce(self, rule_id: str, context: dict = None) -> dict:
        r = self._rules.get(rule_id)
        if not r or not r.enabled:
            return {"enforced": False, "reason": "rule not found or disabled"}
        entry = {"rule": rule_id, "name": r.name, "action": r.action, "time": time.time()}
        self._enforcement_log.append(entry)
        return {"enforced": True, "rule": r.name, "action": r.action, "priority": r.priority}

    def list_rules(self) -> list[dict]:
        return [{"id": r.id, "name": r.name, "description": r.description,
                 "action": r.action, "enabled": r.enabled, "priority": r.priority}
                for r in sorted(self._rules.values(), key=lambda x: x.priority)]

    def log(self, limit: int = 20) -> list[dict]:
        return [{"rule": e["rule"], "name": e["name"], "action": e["action"],
                 "time": time.strftime("%H:%M:%S", time.localtime(e["time"]))}
                for e in self._enforcement_log[-limit:]]

sheriff = Sheriff()
