import time, json, hashlib, random, math
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

# ==============================
# 1. VOTING / CONSENSUS ENGINE
# ==============================

@dataclass
class Vote:
    id: str
    title: str
    description: str
    options: list
    created_by: str = ""
    status: str = "open"
    votes: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

class VotingEngine:
    def __init__(self):
        self._votes: dict[str, Vote] = {}
        self._ballots: dict[str, dict] = {}

    def create_vote(self, title: str, description: str, options: list, created_by: str = "") -> str:
        vid = hashlib.md5(f"{title}:{time.time()}".encode()).hexdigest()[:8]
        self._votes[vid] = Vote(vid, title, description, options, created_by)
        return vid

    def cast_vote(self, vote_id: str, voter: str, choice: str) -> bool:
        vote = self._votes.get(vote_id)
        if not vote or vote.status != "open":
            return False
        if choice not in vote.options:
            return False
        vote.votes[voter] = choice
        return True

    def close_vote(self, vote_id: str) -> Optional[dict]:
        vote = self._votes.get(vote_id)
        if not vote: return None
        vote.status = "closed"
        tally = {opt: 0 for opt in vote.options}
        for v in vote.votes.values():
            if v in tally: tally[v] += 1
        total = sum(tally.values())
        winner = max(tally, key=tally.get) if tally else None
        return {
            "id": vote_id, "title": vote.title, "options": vote.options,
            "tally": tally, "total_votes": total, "winner": winner,
            "turnout": f"{total} voters",
        }

    def list_votes(self) -> list[dict]:
        return [{"id": v.id, "title": v.title, "status": v.status, "options": len(v.options),
                 "votes": len(v.votes), "created_by": v.created_by}
                for v in self._votes.values()]

    def get_vote(self, vote_id: str) -> Optional[dict]:
        v = self._votes.get(vote_id)
        if not v: return None
        tally = {opt: 0 for opt in v.options}
        for cv in v.votes.values():
            if cv in tally: tally[cv] += 1
        return {
            "id": v.id, "title": v.title, "description": v.description,
            "options": v.options, "status": v.status, "tally": tally,
            "total_votes": len(v.votes), "created_by": v.created_by,
        }

    # --- UI-compatible aliases ---
    def list_open(self) -> list[dict]:
        return [{"id": v.id, "topic": v.title, "status": v.status, "options": v.options,
                 "votes": len(v.votes), "total": len(v.votes), "created_by": v.created_by}
                for v in self._votes.values() if v.status == "open"]

    def create_vote_simple(self, topic: str, options: list = None, description: str = "") -> str:
        return self.create_vote(topic, description or topic, options or ["yes", "no"], "ui")

    def cast(self, vote_id: str, voter: str, choice: str) -> bool:
        return self.cast_vote(vote_id, voter, choice)

    def close(self, vote_id: str) -> Optional[dict]:
        result = self.close_vote(vote_id)
        if not result: return None
        return {"id": result["id"], "topic": result["title"], "counts": result["tally"],
                "winner": result["winner"], "options": result["options"],
                "weighted": {k: float(v) for k, v in result["tally"].items()}}

    def all_votes(self) -> list[dict]:
        return [{"id": v.id, "topic": v.title, "status": v.status, "total": len(v.votes)}
                for v in self._votes.values()]

voting_engine = VotingEngine()

# ==============================
# 2. LOGIC PROBE
# ==============================

class LogicProbe:
    def __init__(self):
        self._contradictions: list[dict] = []
        self._flagged_thoughts: list[dict] = []

    def flag_contradiction(self, agent_id: str, claim_a: str, claim_b: str, severity: float = 0.5):
        entry = {
            "id": hashlib.md5(f"{agent_id}:{time.time()}".encode()).hexdigest()[:8],
            "agent": agent_id, "claim_a": claim_a, "claim_b": claim_b,
            "severity": severity, "timestamp": time.time(), "resolved": False,
        }
        self._contradictions.append(entry)
        return entry["id"]

    def flag_thought(self, agent_id: str, thought: str, reason: str, danger_level: str = "low"):
        entry = {
            "id": hashlib.md5(f"thought:{agent_id}:{time.time()}".encode()).hexdigest()[:8],
            "agent": agent_id, "thought": thought, "reason": reason,
            "danger_level": danger_level, "timestamp": time.time(),
        }
        self._flagged_thoughts.append(entry)
        return entry["id"]

    def resolve_contradiction(self, contradiction_id: str):
        for c in self._contradictions:
            if c["id"] == contradiction_id:
                c["resolved"] = True
                return True
        return False

    def get_contradictions(self, unresolved_only: bool = True) -> list[dict]:
        items = [c for c in self._contradictions if not c["resolved"]] if unresolved_only else self._contradictions
        return sorted(items, key=lambda x: -x["severity"])[:20]

    def get_flagged(self, min_danger: str = "low") -> list[dict]:
        levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        threshold = levels.get(min_danger, 0)
        return [t for t in self._flagged_thoughts if levels.get(t["danger_level"], 0) >= threshold][:20]

    def stats(self) -> dict:
        return {
            "total_contradictions": len(self._contradictions),
            "unresolved": sum(1 for c in self._contradictions if not c["resolved"]),
            "flagged_thoughts": len(self._flagged_thoughts),
            "critical_flags": sum(1 for t in self._flagged_thoughts if t["danger_level"] == "critical"),
        }

logic_probe = LogicProbe()

# ==============================
# 3. SENTINEL MONITOR
# ==============================

class SentinelMonitor:
    def __init__(self):
        self._health_history: list[dict] = []
        self._alerts: list[dict] = []

    def check(self) -> dict:
        from config import council, api_configs
        from safety_engine import stop_light
        from scheduler_engine import scheduler
        from memory_engine import l1_memory, thought_vdb
        subsystems = {
            "router": True,
            "scheduler": scheduler.stats()["queue_size"] < 100,
            "memory": len(l1_memory._store) < 1000,
            "thought_vdb": len(thought_vdb._vectors) < 500,
            "stop_light": stop_light.status() == "green",
            "council": council.num_ceos > 0,
            "api_configs": len(api_configs) > 0,
        }
        status = "healthy" if all(subsystems.values()) else "degraded"
        timestamp = time.time()
        entry = {"timestamp": timestamp, "status": status, "subsystems": dict(subsystems)}
        self._health_history.append(entry)
        return entry

    def alert(self, source: str, message: str, severity: str = "warning"):
        alert = {
            "id": hashlib.md5(f"{source}:{time.time()}".encode()).hexdigest()[:8],
            "source": source, "message": message, "severity": severity,
            "timestamp": time.time(), "acknowledged": False,
        }
        self._alerts.append(alert)
        return alert["id"]

    def acknowledge(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a["id"] == alert_id:
                a["acknowledged"] = True
                return True
        return False

    def recent_health(self, count: int = 5) -> list[dict]:
        return self._health_history[-count:]

    def active_alerts(self) -> list[dict]:
        return [a for a in self._alerts if not a["acknowledged"]]

    def stats(self) -> dict:
        h = self._health_history
        healthy_count = sum(1 for e in h if e["status"] == "healthy")
        return {
            "checks": len(h),
            "healthy_rate": healthy_count / max(len(h), 1),
            "active_alerts": len(self.active_alerts()),
            "total_alerts": len(self._alerts),
            "current_status": h[-1]["status"] if h else "unknown",
        }

sentinel = SentinelMonitor()

# ==============================
# 4. SHERIFF RULE MANAGER
# ==============================

DEFAULT_RULES = [
    {"id": "R1", "name": "No dangerous code", "description": "Agents must not generate code that could cause harm", "severity": "critical", "enabled": True},
    {"id": "R2", "name": "Confidence threshold", "description": "All responses must meet minimum confidence threshold", "severity": "high", "enabled": True},
    {"id": "R3", "name": "Budget compliance", "description": "Token usage must stay within allocated budget", "severity": "high", "enabled": True},
    {"id": "R4", "name": "Safety first", "description": "Safety subsystem must be green before execution", "severity": "critical", "enabled": True},
    {"id": "R5", "name": "No hallucinations", "description": "Agents must not fabricate facts or references", "severity": "critical", "enabled": True},
    {"id": "R6", "name": "Cache freshness", "description": "Cached results older than 5 min must be re-validated", "severity": "medium", "enabled": True},
    {"id": "R7", "name": "Agent timeouts", "description": "Agents must complete within configured timeout", "severity": "medium", "enabled": True},
    {"id": "R8", "name": "ELO minimum", "description": "Agents below 800 ELO require review", "severity": "low", "enabled": False},
]

class SheriffRulebook:
    def __init__(self):
        self._rules: list[dict] = [dict(r) for r in DEFAULT_RULES]

    def list_rules(self) -> list[dict]:
        return self._rules

    def get_rule(self, rule_id: str) -> Optional[dict]:
        for r in self._rules:
            if r["id"] == rule_id: return r
        return None

    def add_rule(self, name: str, description: str, severity: str = "medium") -> str:
        rid = f"R{len(self._rules)+1}"
        self._rules.append({"id": rid, "name": name, "description": description, "severity": severity, "enabled": True})
        return rid

    def remove_rule(self, rule_id: str) -> bool:
        for i, r in enumerate(self._rules):
            if r["id"] == rule_id:
                self._rules.pop(i)
                return True
        return False

    def toggle_rule(self, rule_id: str) -> bool:
        r = self.get_rule(rule_id)
        if r:
            r["enabled"] = not r["enabled"]
            return True
        return False

    def edit_rule(self, rule_id: str, name: str = "", description: str = "", severity: str = "") -> bool:
        r = self.get_rule(rule_id)
        if not r: return False
        if name: r["name"] = name
        if description: r["description"] = description
        if severity: r["severity"] = severity
        return True

    # --- UI-compatible aliases ---
    def add_rule(self, name: str, description: str = "", action: str = "", priority: int = 5) -> str:
        rid = f"R{len(self._rules)+1}"
        sev = "critical" if priority >= 9 else "high" if priority >= 7 else "medium" if priority >= 4 else "low"
        self._rules.append({"id": rid, "name": name, "description": description or action,
                           "severity": sev, "priority": priority, "action": action, "enabled": True})
        return rid

    def toggle(self, rule_id: str) -> Optional[bool]:
        r = self.get_rule(rule_id)
        if r:
            r["enabled"] = not r["enabled"]
            return r["enabled"]
        return None

    def check_violations(self) -> list[dict]:
        violations = []
        for r in self._rules:
            if not r["enabled"]: continue
            violations.append({"rule": r["name"], "severity": r["severity"], "status": "pending_review"})
        return violations

sheriff = SheriffRulebook()

# ==============================
# 5. SESSION MANAGER
# ==============================

@dataclass
class Session:
    id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    task_count: int = 0
    token_used: int = 0
    success_count: int = 0
    fail_count: int = 0
    notes: str = ""

class SessionManager:
    def __init__(self):
        self._sessions: list[Session] = []
        self._current: Optional[Session] = None

    def start_session(self, notes: str = "") -> str:
        sid = hashlib.md5(f"session:{time.time()}".encode()).hexdigest()[:12]
        self._current = Session(id=sid, notes=notes)
        self._sessions.append(self._current)
        return sid

    def end_session(self):
        if self._current:
            self._current.end_time = time.time()
            self._current = None

    def record_task(self, success: bool, tokens: int = 0):
        if self._current:
            self._current.task_count += 1
            self._current.token_used += tokens
            if success: self._current.success_count += 1
            else: self._current.fail_count += 1

    def current_session(self) -> Optional[dict]:
        if not self._current: return None
        dur = time.time() - self._current.start_time
        return {
            "id": self._current.id, "duration_s": round(dur, 1),
            "tasks": self._current.task_count, "tokens": self._current.token_used,
            "success_rate": self._current.success_count / max(self._current.task_count, 1),
            "notes": self._current.notes,
        }

    def list_sessions(self, limit: int = 10) -> list[dict]:
        return [{
            "id": s.id, "start": time.strftime("%H:%M:%S", time.localtime(s.start_time)),
            "end": time.strftime("%H:%M:%S", time.localtime(s.end_time)) if s.end_time else "active",
            "tasks": s.task_count, "tokens": s.token_used,
            "success_rate": s.success_count / max(s.task_count, 1),
            "notes": s.notes[:40],
        } for s in self._sessions[-limit:]]

    def stats(self) -> dict:
        total_tasks = sum(s.task_count for s in self._sessions)
        total_tokens = sum(s.token_used for s in self._sessions)
        total_success = sum(s.success_count for s in self._sessions)
        return {
            "total_sessions": len(self._sessions),
            "active": 1 if self._current else 0,
            "total_tasks": total_tasks,
            "total_tokens": total_tokens,
            "overall_success_rate": total_success / max(total_tasks, 1),
        }

session_manager = SessionManager()

# ==============================
# 6. COGNITIVE CONTROLS
# ==============================

class CognitiveControls:
    def __init__(self):
        self.incubation_heat: float = 0.1
        self.incubation_max_ideas: int = 100
        self.wander_steps: int = 3
        self.analogical_top_k: int = 3
        self.friction_dial: int = 5
        self.rem_cycle_enabled: bool = True
        self.rem_interval_s: float = 300.0

    def set_friction(self, value: int):
        self.friction_dial = max(0, min(10, value))

    def set_incubation_heat(self, value: float):
        self.incubation_heat = max(0.0, min(1.0, value))

    def toggle_rem(self):
        self.rem_cycle_enabled = not self.rem_cycle_enabled

    def to_dict(self) -> dict:
        return {
            "incubation_heat": self.incubation_heat,
            "incubation_max_ideas": self.incubation_max_ideas,
            "wander_steps": self.wander_steps,
            "analogical_top_k": self.analogical_top_k,
            "friction_dial": self.friction_dial,
            "rem_cycle": "enabled" if self.rem_cycle_enabled else "disabled",
            "rem_interval_s": self.rem_interval_s,
        }

    # --- UI-compatible aliases ---
    def get_settings(self) -> dict:
        return self.to_dict()

    def set_friction(self, value: float):
        self.friction_dial = max(0, min(10, int(value * 10)))

    def set_heat(self, value: float):
        self.incubation_heat = max(0.0, min(1.0, value))

cognitive_controls = CognitiveControls()

# ==============================
# 7. PBT EVOLUTION VISUALIZER
# ==============================

class EvolutionTracker:
    def __init__(self):
        self._history: list[dict] = []

    def record_generation(self, gen: int, population: int, best_fitness: float, avg_fitness: float, diversity: float = 0.0):
        self._history.append({
            "generation": gen, "population": population,
            "best_fitness": best_fitness, "avg_fitness": avg_fitness,
            "diversity": diversity, "timestamp": time.time(),
        })

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    def fitness_graph(self, width: int = 40) -> str:
        if not self._history:
            return "(no data)"
        bests = [h["best_fitness"] for h in self._history]
        avgs = [h["avg_fitness"] for h in self._history]
        max_val = max(max(bests), max(avgs), 0.01)
        lines = ["Fitness over generations:", "", f"{'Gen':>4} {'Best':>6} {'Avg':>6}  {'Graph':<{width}}"]
        for i in range(len(self._history)):
            h = self._history[i]
            b_bar = int((h["best_fitness"] / max_val) * (width - 4))
            a_bar = int((h["avg_fitness"] / max_val) * (width - 4))
            line = f"{h['generation']:>4} {h['best_fitness']:>6.3f} {h['avg_fitness']:>6.3f}  {'█'*b_bar}{'░'*a_bar}"
            lines.append(line)
        return "\n".join(lines)

    def stats(self) -> dict:
        if not self._history:
            return {"generations": 0}
        return {
            "generations": len(self._history),
            "latest_gen": self._history[-1]["generation"],
            "all_time_best": max(h["best_fitness"] for h in self._history),
            "avg_of_avgs": sum(h["avg_fitness"] for h in self._history) / len(self._history),
        }

    # --- UI-compatible aliases ---
    def get_status(self) -> dict:
        return self.stats()

    def get_history(self) -> list[dict]:
        return [{"gen": h["generation"], "best_fitness": h["best_fitness"],
                 "avg_fitness": h["avg_fitness"], "population": h["population"],
                 "diversity": h.get("diversity", 0.0)}
                for h in self._history]

    def get_population(self) -> list[dict]:
        return [{"name": f"genome_{h['generation']}", "fitness": h["best_fitness"]}
                for h in self._history[-5:]]

pbt_tracker = EvolutionTracker()

# ==============================
# 8. TRAINING CONTROLS
# ==============================

@dataclass
class TrainingTask:
    id: str
    name: str
    type: str
    status: str = "pending"
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)

class TrainingPipeline:
    def __init__(self):
        self._tasks: list[TrainingTask] = []
        self._gold_repos: list[dict] = []
        self._pattern_db: list[dict] = []

    def add_task(self, name: str, task_type: str) -> str:
        tid = hashlib.md5(f"train:{name}:{time.time()}".encode()).hexdigest()[:8]
        self._tasks.append(TrainingTask(tid, name, task_type))
        return tid

    def update_progress(self, task_id: str, progress: float):
        for t in self._tasks:
            if t.id == task_id:
                t.progress = min(1.0, max(0.0, progress))
                if progress >= 1.0: t.status = "completed"
                elif progress > 0: t.status = "running"
                return True
        return False

    def add_gold_repo(self, name: str, url: str, domain: str = ""):
        self._gold_repos.append({"name": name, "url": url, "domain": domain, "added": time.time()})

    def add_pattern(self, name: str, pattern: str, category: str = ""):
        pid = hashlib.md5(f"pattern:{name}".encode()).hexdigest()[:8]
        self._pattern_db.append({"id": pid, "name": name, "pattern": pattern, "category": category, "added": time.time()})

    def list_tasks(self) -> list[dict]:
        return [{"id": t.id, "name": t.name, "type": t.type, "status": t.status, "progress": f"{t.progress:.0%}"} for t in self._tasks]

    def list_repos(self) -> list[dict]:
        return self._gold_repos

    def list_patterns(self, category: str = "") -> list[dict]:
        if category: return [p for p in self._pattern_db if p["category"] == category]
        return self._pattern_db

    def stats(self) -> dict:
        return {
            "tasks": len(self._tasks),
            "running": sum(1 for t in self._tasks if t.status == "running"),
            "completed": sum(1 for t in self._tasks if t.status == "completed"),
            "gold_repos": len(self._gold_repos),
            "patterns": len(self._pattern_db),
        }

    # --- UI-compatible aliases ---
    def get_tasks(self) -> list[dict]:
        return self.list_tasks()

    def add_repo(self, url: str) -> str:
        self.add_gold_repo(url, url, "general")
        return f"repo-{hashlib.md5(url.encode()).hexdigest()[:8]}"

    def gold_stats(self) -> dict:
        return {"total_gold": len(self._gold_repos), "total_distillations": 0,
                "total_patterns": len(self._pattern_db),
                "domains": list(set(r["domain"] for r in self._gold_repos))}

    def list_gold(self) -> list[dict]:
        return [{"id": f"gold-{i}", "name": r["name"], "domain": r["domain"],
                 "content": r["url"][:80]}
                for i, r in enumerate(self._gold_repos)]

    def store_pattern(self, key: str, pattern: str):
        self.add_pattern(key, pattern, "general")

    def get_all_patterns(self) -> list[dict]:
        return [{"key": p["name"], "value": p["pattern"]} for p in self._pattern_db]

    def add_gold(self, name: str, content: str, domain: str = "general") -> str:
        self.add_gold_repo(name, content, domain)
        return hashlib.md5(f"gold:{name}".encode()).hexdigest()[:8]

training = TrainingPipeline()
