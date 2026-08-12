import json
import time
import hashlib
import heapq
from typing import Optional
from config import cfg, TokenBudget
from blackboard import blackboard, internal_notes

_elo_ratings: dict[str, float] = {}
_run_log: list[dict] = []
_contradictions: list[dict] = []
_postmortems: list[dict] = []
_experience_replay_queue: list[tuple] = []
_experience_counter = 0

def _run_id(problem: str) -> str:
    return hashlib.md5(f"{time.time()}:{problem}".encode()).hexdigest()[:12]

def record_run(problem: str, solution: str, outcome: str, agents_used: list, confidence: float, tokens: int, duration_ms: int) -> dict:
    entry = {
        "run_id": _run_id(problem),
        "problem": problem[:200],
        "solution_summary": solution[:200],
        "outcome": outcome,
        "confidence": confidence,
        "tokens": tokens,
        "duration_ms": duration_ms,
        "agents": [a.get("role", a.get("id", "unknown")) for a in agents_used],
        "agent_count": len(agents_used),
        "timestamp": time.time(),
    }
    _run_log.append(entry)
    blackboard.write(f"run:{entry['run_id']}", json.dumps(entry), "learn", confidence)
    return entry

def update_elo(agent_role: str, won: bool, k: int = 32):
    rating = _elo_ratings.get(agent_role, 1200.0)
    expected = 1.0 / (1.0 + 10.0 ** ((1200 - rating) / 400.0))
    new_rating = rating + k * (1.0 if won else 0.0 - expected)
    _elo_ratings[agent_role] = new_rating

def elo_summary() -> dict:
    return dict(sorted(_elo_ratings.items(), key=lambda x: -x[1])[:20])

def write_postmortem(problem: str, solution: str, outcome: str, agents_used: list, confidence: float) -> dict:
    pm = {
        "id": _run_id(problem),
        "worked": f"Role {agents_used[0].get('role','?') if agents_used else '?'} contributed, confidence {confidence:.2f}",
        "didnt": "No dead ends" if outcome == "success" else "Solution was rejected or low confidence",
        "surprising": "Parallel agents converged on similar answers" if confidence > 0.8 else "Agents disagreed on approach",
        "faster_next": f"Increase agent count for deeper exploration" if outcome != "success" else "Cache routing decision for similar problems",
        "outcome": outcome,
        "timestamp": time.time(),
    }
    _postmortems.append(pm)
    return pm

def find_contradictions() -> list[dict]:
    return _contradictions[-20:]

def learn(problem: str, solution: str, outcome: str, agents_used: list,
          confidence: float = 0.75, tokens: int = 0, duration_ms: int = 0) -> dict:
    global _experience_counter

    entry = record_run(problem, solution, outcome, agents_used, confidence, tokens, duration_ms)
    for a in agents_used:
        role = a.get("role", a.get("id", "unknown"))
        update_elo(role, outcome in ("success", "completed"))

    pm = write_postmortem(problem, solution, outcome, agents_used, confidence)

    contradictions = find_contradictions()

    _experience_counter += 1
    replay_entry = (_experience_counter, entry)
    heapq.heappush(_experience_replay_queue, replay_entry)

    learned_pattern = {
        "pattern_id": entry["run_id"],
        "problem_type": problem[:60],
        "outcome": outcome,
        "agents_used": len(agents_used),
        "confidence": confidence,
    }

    internal_notes.write("learn", f"Learned from run {entry['run_id']}: {outcome} (conf={confidence:.2f})", "public", confidence)

    return {
        "learned": True,
        "run_id": entry["run_id"],
        "elo_updated": elo_summary(),
        "postmortem": pm,
        "contradictions": contradictions,
        "replay_queue_size": len(_experience_replay_queue),
        "total_runs": len(_run_log),
        "total_postmortems": len(_postmortems),
        "pattern": learned_pattern,
        "budget_advice": "Consider using flash/small models for routine tasks" if outcome == "success" else "Consider deeper agent tree for complex problems",
    }

def get_stats() -> dict:
    return {
        "total_runs": len(_run_log),
        "total_postmortems": len(_postmortems),
        "elo_ratings": elo_summary(),
        "replay_queue": len(_experience_replay_queue),
        "contradictions": len(_contradictions),
        "success_rate": sum(1 for r in _run_log if r["outcome"] in ("success", "completed")) / max(len(_run_log), 1),
        "avg_confidence": sum(r["confidence"] for r in _run_log[-100:]) / max(len(_run_log[-100:]), 1),
        "avg_tokens": sum(r["tokens"] for r in _run_log[-100:]) / max(len(_run_log[-100:]), 1),
    }
