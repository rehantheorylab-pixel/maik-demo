import time
import json
import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CircuitBreaker:
    name: str
    threshold: int = 3
    cooldown_s: float = 60.0
    _failures: list = field(default_factory=list)
    _tripped: bool = False
    _tripped_at: float = 0.0

    @property
    def tripped(self) -> bool:
        if self._tripped and time.time() - self._tripped_at > self.cooldown_s:
            self._tripped = False
            self._failures = []
        return self._tripped

    def record_failure(self, detail: str = ""):
        self._failures.append({"time": time.time(), "detail": detail})
        if len(self._failures) >= self.threshold:
            self._tripped = True
            self._tripped_at = time.time()

    def vibration(self) -> float:
        if not self._failures:
            return 0.0
        recent = [f for f in self._failures if time.time() - f["time"] < 300]
        return len(recent) / max(self.threshold, 1)

class SafetyTriad:
    def __init__(self):
        self._opinions: dict[str, list[dict]] = {}

    def record_opinion(self, problem_hash: str, agent_id: str, verdict: str, confidence: float):
        self._opinions.setdefault(problem_hash, []).append(
            {"agent": agent_id, "verdict": verdict, "confidence": confidence, "time": time.time()}
        )

    def majority_verdict(self, problem_hash: str) -> Optional[str]:
        opinions = self._opinions.get(problem_hash, [])
        if len(opinions) < 3:
            return None
        votes = {}
        for o in opinions:
            votes[o["verdict"]] = votes.get(o["verdict"], 0) + o["confidence"]
        total = sum(votes.values())
        if not total:
            return None
        for verdict, score in votes.items():
            if score / total > 0.5:
                return verdict
        return None

    def disagreement_level(self, problem_hash: str) -> float:
        opinions = self._opinions.get(problem_hash, [])
        if len(opinions) < 2:
            return 0.0
        verdicts = [o["verdict"] for o in opinions]
        unique = len(set(verdicts))
        return (unique - 1) / 2.0

_safety_triad = SafetyTriad()

@dataclass
class StopLight:
    green_until: float = field(default_factory=lambda: time.time() + 3600)
    yellow_until: float = 0.0
    red_until: float = 0.0

    def status(self) -> str:
        now = time.time()
        if now < self.green_until:
            return "green"
        if now < self.yellow_until:
            return "yellow"
        return "red"

    def set_yellow(self, duration_s: float = 300):
        now = time.time()
        self.yellow_until = now + duration_s
        if self.green_until > now:
            self.green_until = now

    def set_red(self, duration_s: float = 600):
        now = time.time()
        self.red_until = now + duration_s
        self.green_until = now
        self.yellow_until = now

    def set_green(self):
        self.green_until = time.time() + 3600

stop_light = StopLight()

class MonotonicConfidence:
    def __init__(self):
        self._seen: dict[str, dict] = {}

    def record(self, problem_hash: str, outcome: str, confidence: float):
        prev = self._seen.get(problem_hash)
        if prev and outcome == "failure":
            prev["repeat_count"] = prev.get("repeat_count", 0) + 1
            prev["last_seen"] = time.time()
        else:
            self._seen[problem_hash] = {"outcome": outcome, "confidence": confidence, "repeat_count": 0, "last_seen": time.time()}

    def repeat_count(self, problem_hash: str) -> int:
        entry = self._seen.get(problem_hash)
        return entry["repeat_count"] if entry else 0

    def should_skip(self, problem_hash: str) -> bool:
        entry = self._seen.get(problem_hash)
        if not entry:
            return False
        return entry["repeat_count"] >= 2 and entry["outcome"] == "failure"

monotonic = MonotonicConfidence()

IMPURE_PATTERNS = [
    r"(?i)(api[_-]?key|secret[_-]?key|password)\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)(BEGIN\s+(RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY)",
    r"rm\s+-rf\s+/\s*(;|\||&&)",
    r"(?i)(DROP|TRUNCATE)\s+TABLE",
    r"(?i)(sudo\s+)?(chmod\s+777|chown\s+\S+\s+/)",
]

class AntiPatternChecker:
    def check(self, text: str) -> list[dict]:
        findings = []
        for pattern in IMPURE_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                findings.append({"pattern": pattern[:40], "match_count": len(matches)})
        return findings

anti_pattern = AntiPatternChecker()

class KillSwitch:
    def __init__(self, filepath: str = ""):
        self._filepath = filepath or ""
        self._internal_kill = False

    def check(self) -> bool:
        if self._internal_kill:
            return True
        if self._filepath:
            import os
            return os.path.exists(self._filepath)
        return False

    def activate(self):
        self._internal_kill = True

    def deactivate(self):
        self._internal_kill = False

kill_switch = KillSwitch()
