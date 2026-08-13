"""Prompt Management Agent (Phase J).

The CEO's prompt department. Its only job: write, upgrade, and grade the
system prompts of every other agent in the org — so prompt quality is a
managed asset, not a guessing game.

Workflows:
  write  — compose a new agent prompt from a role + mission, graded before
           it is ever assigned to an agent.
  review — grade an existing prompt against the quality checklist.
  upgrade — take a low-scoring prompt, diagnose weaknesses, rewrite it,
            re-grade; repeat until it passes the quality bar.
  report — org-wide prompt health dashboard (per-node grades, weakest
           links, upgrade history).

Every action runs in the dry-run/grade-first discipline: no prompt is
assigned to a live node unless its grade passes the configured bar.
Prompts are stored in PromptSystem as `pm:{node_uid}` entries with full
history, so the CEO can always roll back (`prompt_history`).
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .prompt_system import PromptSystem

QUALITY_WEIGHTS = {
    "identity": 2.0,        # knows who it is
    "role_clarity": 2.0,    # knows exactly what to do
    "constraints": 1.5,     # knows its limits & permissions
    "output_format": 1.5,   # knows what good output looks like
    "error_handling": 1.0,  # knows what to do when stuck
    "coordination": 1.0,    # knows how to talk to the team
    "mission": 1.5,         # has an explicit mission statement
    "tone": 0.5,            # professional, unambiguous
}
MAX_QUALITY = sum(QUALITY_WEIGHTS.values())
DEFAULT_PASS_BAR = 0.75      # grade threshold for assigning a prompt
MAX_UPGRADE_ROUNDS = 3       # safety cap


@dataclass
class GradeResult:
    grade: float             # 0.0-1.0 weighted quality score
    criteria: Dict[str, Tuple[bool, str]]  # criterion -> (met, note)
    suggestions: List[str]
    prompt_text: str
    timestamp: float = field(default_factory=time.time)


class PromptManagement:
    """The prompt department: write/grade/upgrade/promote prompts."""

    def __init__(self, prompt_system: PromptSystem,
                 pass_bar: float = DEFAULT_PASS_BAR,
                 base: Optional[Path] = None):
        self.ps = prompt_system
        self.pass_bar = pass_bar
        self.base = Path(base) if base else Path(
            os.environ.get("MAIK_DATA_DIR", ".")) / "prompt_dept"
        self.base.mkdir(parents=True, exist_ok=True)
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self._load_history()

    # ------------------------------------------------------------ grading
    def grade(self, prompt_text: str) -> GradeResult:
        """Deterministic structural grading of a system prompt."""
        criteria: Dict[str, Tuple[bool, str]] = {}
        low = prompt_text.lower()

        identity = bool(re.search(r"you are (an?|the) ", low))
        criteria["identity"] = (identity, "has/h lacks a 'You are...' identity line")

        role = ("task" in low or "goal" in low or "responsib" in low or
                "write" in low or "code" in low or "test" in low)
        criteria["role_clarity"] = (role, "role/tasks mentioned explicitly")

        constraints = bool(re.search(r"(must not|never|do not|forbidden|"
                                     r"without (asking|permission)|only)", low))
        criteria["constraints"] = (constraints, "explicit constraints/limits")

        outfmt = bool(re.search(r"(format|output|respond with|return|json|"
                                r"bullet|numbered|markdown)", low))
        criteria["output_format"] = (outfmt, "output format specified")

        err = bool(re.search(r"(if (you|you are) (unsure|stuck|cannot)|"
                             r"when (you|an )?error|ask (for|the)|escalat)", low))
        criteria["error_handling"] = (err, "what-to-do-when-stuck guidance")

        coord = bool(re.search(r"(thread|notebook|blackboard|manager|ceo|"
                               r"sibling|report|team|coordinate)", low))
        criteria["coordination"] = (coord, "team coordination hooks")

        mission = bool(re.search(r"(mission|objective|your goal is|your job "
                                 r"is)", low))
        criteria["mission"] = (mission, "explicit mission statement")

        tone = (len(prompt_text.split()) >= 20 and
                not re.search(r"(lol|haha|omg|!!!{3,})", prompt_text))
        criteria["tone"] = (tone, "professional length and tone")

        score = sum(w for c, (met, _) in criteria.items()
                    if met for w in (QUALITY_WEIGHTS.get(c, 0),))
        suggestions = [f"{c}: {note}" for c, (met, note) in criteria.items()
                       if not met]
        return GradeResult(grade=round(score / MAX_QUALITY, 3),
                           criteria=criteria, suggestions=suggestions,
                           prompt_text=prompt_text)

    # ------------------------------------------------------------ writing
    def write(self, role: str, mission: str, node_uid: str = "",
              powers: Optional[List[str]] = None) -> dict:
        """Compose a quality-first prompt draft for a role + mission."""
        powers = powers or []
        base_text = self._role_text(role)
        draft = (
            f"You are the {role} specialist in MAIK.\n"
            f"MISSION: {mission}\n"
            f"{base_text}\n"
            f"CONSTRAINTS:\n"
            f"- Never fabricate facts; say 'I don't know' when unsure.\n"
            f"- Output format: clear answer first, then brief reasoning.\n"
            f"- If stuck after 3 attempts, report to your manager instead of looping.\n"
            f"COORDINATION:\n"
            f"- Use your public notebook to record key decisions; use threads "
            f"to propose and debate ideas with siblings.\n"
            f"- Escalate blockers to your manager with context, not complaints.\n"
            f"{'PERMISSIONS: ' + ', '.join(powers) if powers else ''}"
        )
        g = self.grade(draft)
        result = {"draft": draft, "grade": g.grade,
                  "passes": g.grade >= self.pass_bar,
                  "suggestions": g.suggestions}
        if node_uid:
            self._record_history(f"pm:{node_uid}", "write",
                                 {"grade": g.grade, "draft": draft[:400]})
        return result

    # ------------------------------------------------------------ review
    def review(self, node_uid: str) -> dict:
        """Grade the currently resolved prompt for a node."""
        sp = self.ps.get(f"node:{node_uid}") or self.ps.get(f"pm:{node_uid}")
        text = sp.text if sp is not None else ""
        g = self.grade(text)
        return {"node_uid": node_uid, "grade": g.grade,
                "passes": g.grade >= self.pass_bar,
                "suggestions": g.suggestions,
                "criteria": {k: v[0] for k, v in g.criteria.items()}}

    # ------------------------------------------------------------ upgrade
    def upgrade(self, node_uid: str) -> dict:
        """Diagnose a low-scoring prompt and rewrite it until it passes.

        Applied deterministically: each failed criterion maps to a concrete
        fix injected into the text. Max MAX_UPGRADE_ROUNDS rounds.
        """
        with self._lock:
            sp = self.ps.get(f"org:{node_uid}") or self.ps.get(f"pm:{node_uid}")
            if sp is None:
                return {"error": "no custom prompt found for node"}
            text = sp.text
            log = []
            for i in range(MAX_UPGRADE_ROUNDS):
                g = self.grade(text)
                if g.grade >= self.pass_bar:
                    log.append({"round": i, "grade": g.grade, "action": "pass"})
                    break
                fixes = self._fix_text(text, g)
                if fixes == text:
                    log.append({"round": i, "grade": g.grade,
                                "action": "no_more_fixes"})
                    break
                text = fixes
                log.append({"round": i, "grade": g.grade, "action": "rewrote"})
            final = self.grade(text)
            self.ps.update_text(f"pm:{node_uid}", text, editor="prompt-dept")
            self._record_history(f"pm:{node_uid}", "upgrade",
                                 {"grade_before": log[0]["grade"] if log else 0,
                                  "grade_after": final.grade, "rounds": len(log)})
            return {"node_uid": node_uid, "grade_before": log[0]["grade"] if log else 0,
                    "grade_after": final.grade, "passes": final.grade >= self.pass_bar,
                    "log": log, "prompt": text}

    # ------------------------------------------------------------ report
    def report(self) -> dict:
        nodes = [e for e in self._history]
        return {"history_size": sum(len(v) for v in self._history.values()),
                "nodes_tracked": len(nodes)}

    def prompt_history(self, node_uid: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history.get(f"pm:{node_uid}", []))

    # ------------------------------------------------------------ internals
    def _role_text(self, role: str) -> str:
        sp = self.ps.get(f"role:{role}")
        return sp.text if sp is not None else f"You are the {role} specialist."
    def _fix_text(self, text: str, g: GradeResult) -> str:
        additions = []
        failed = [c for c, (met, _) in g.criteria.items() if not met]
        if "identity" in failed:
            additions.append("You are a MAIK agent with a clear identity.")
        if "constraints" in failed:
            additions.append("CONSTRAINTS: Never fabricate facts. If unsure, "
                             "say so instead of guessing.")
        if "output_format" in failed:
            additions.append("OUTPUT FORMAT: state the answer first, then "
                             "brief reasoning.")
        if "error_handling" in failed:
            additions.append("IF STUCK: after 3 attempts, report to your "
                             "manager with full context.")
        if "coordination" in failed:
            additions.append("COORDINATION: use threads to debate ideas and "
                             "notebooks to record decisions.")
        if "mission" in failed:
            additions.append("MISSION: complete your assigned task to the "
                             "highest standard and report results.")
        if "tone" in failed:
            additions.append("Write professionally and precisely.")
        return text + "\n\n" + "\n".join(additions) if additions else text

    def _record_history(self, key: str, action: str, detail: dict) -> None:
        entry = {"action": action, "ts": time.time(), **detail}
        with self._lock:
            self._history.setdefault(key, []).append(entry)
            self._persist_history()

    def _persist_history(self) -> None:
        (self.base / "history.json").write_text(
            json.dumps(self._history, indent=1))

    def _load_history(self) -> None:
        p = self.base / "history.json"
        if p.exists():
            try:
                self._history = json.loads(p.read_text())
            except (ValueError, OSError):
                self._history = {}
