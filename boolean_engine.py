from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable

class GateOp(Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    XOR = "XOR"
    NAND = "NAND"
    NOR = "NOR"

@dataclass
class AgentGate:
    name: str
    operator: GateOp
    inputs: list[str] = field(default_factory=list)
    output: Optional[str] = None
    threshold: float = 0.5

    def evaluate(self, inputs: dict[str, float]) -> float:
        values = [inputs.get(i, 0.0) for i in self.inputs]
        if self.operator == GateOp.AND:
            result = min(values) if values else 0.0
        elif self.operator == GateOp.OR:
            result = max(values) if values else 0.0
        elif self.operator == GateOp.NOT:
            result = 1.0 - (values[0] if values else 0.0)
        elif self.operator == GateOp.XOR:
            result = (sum(values) % 2) if values else 0.0
        elif self.operator == GateOp.NAND:
            result = 1.0 - (min(values) if values else 0.0)
        elif self.operator == GateOp.NOR:
            result = 1.0 - (max(values) if values else 0.0)
        else:
            result = 0.0
        return 1.0 if result >= self.threshold else 0.0

class AgentCircuit:
    def __init__(self):
        self._gates: dict[str, AgentGate] = {}
        self._wire_values: dict[str, float] = {}

    def add_gate(self, gate: AgentGate):
        self._gates[gate.name] = gate

    def set_input(self, name: str, value: float):
        self._wire_values[name] = value

    def evaluate(self) -> dict[str, float]:
        outputs = {}
        for gname in self._topological_order():
            gate = self._gates[gname]
            result = gate.evaluate(self._wire_values)
            if gate.output:
                self._wire_values[gate.output] = result
            outputs[gname] = result
        return outputs

    def _topological_order(self) -> list[str]:
        visited = set()
        order = []
        def dfs(name):
            if name in visited:
                return
            visited.add(name)
            gate = self._gates[name]
            for inp in gate.inputs:
                if inp in self._gates:
                    dfs(inp)
            order.append(name)
        for name in self._gates:
            dfs(name)
        return order

class NeuralVoter:
    def __init__(self):
        self._weights: dict[str, float] = {}
        self._biases: dict[str, float] = {}

    def register_voter(self, voter_id: str, weight: float = 1.0, bias: float = 0.0):
        self._weights[voter_id] = weight
        self._biases[voter_id] = bias

    def vote(self, votes: dict[str, float]) -> dict:
        total_weight = sum(self._weights.get(v, 1.0) for v in votes)
        if total_weight == 0:
            return {"outcome": "tie", "score": 0.5, "confidence": 0.0}
        weighted_sum = sum(votes.get(v, 0.0) * self._weights.get(v, 1.0) + self._biases.get(v, 0.0) for v in votes)
        avg = weighted_sum / total_weight
        confidence = abs(avg - 0.5) * 2
        outcome = "pass" if avg >= 0.5 else "fail"
        return {"outcome": outcome, "score": avg, "confidence": confidence}

    def adjust_weights(self, voter_id: str, delta: float):
        self._weights[voter_id] = max(0.1, self._weights.get(voter_id, 1.0) + delta)

voter = NeuralVoter()
