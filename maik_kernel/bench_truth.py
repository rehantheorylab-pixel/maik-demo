"""Ground-truth benchmark suite.

Every problem has a verified answer, so runs are judged correct/incorrect —
not just "a dict was returned". This is the Phase-E layer that makes MAIK's
tests certify intelligence instead of structure.

Problems are deterministic (same answer every run) where possible; coding
and research problems judge by substring containment of canonical phrases.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .config import Config
from .executor import Executor
from .learn import LearningSystem
from .memory import MemorySystem
from .pattern_lib import PatternLibrary

JUDGE_EXACT = "exact"            # normalized string equality
JUDGE_CONTAINS = "contains"      # answer must contain canonical tokens
JUDGE_ANY = "any_of"             # answer must contain one of several options


@dataclass
class BenchProblem:
    id: str
    problem: str
    expected: str
    judge: str = JUDGE_CONTAINS
    alternatives: Optional[List[str]] = None   # for any_of judge
    domain: str = "math"
    cost_estimate: float = 0.001


@dataclass
class BenchRow:
    pid: str
    correct: bool
    tier: str
    pattern: Optional[str]
    cost_usd: float
    duration_s: float
    answer: str


class TruthBench:
    DEFAULTS: List[BenchProblem] = [
        # --- math (exact) ---
        BenchProblem("m1", "Calculate 17 x 23", "391", JUDGE_EXACT, domain="math"),
        BenchProblem("m2", "What is 125 + 275", "400", JUDGE_EXACT, domain="math"),
        BenchProblem("m3", "1000 minus 387 equals", "613", JUDGE_EXACT, domain="math"),
        BenchProblem("m4", "What is 144 divided by 12", "12", JUDGE_EXACT, domain="math"),
        BenchProblem("m5", "Compute 2 to the power of 10", "1024", JUDGE_EXACT, domain="math"),
        BenchProblem("m6", "Square root of 169", "13", JUDGE_EXACT, domain="math"),
        BenchProblem("m7", "What is 7 factorial (7!)", "5040", JUDGE_EXACT, domain="math"),
        BenchProblem("m8", "Sum of integers from 1 to 50", "1275", JUDGE_EXACT, domain="math"),
        BenchProblem("m9", "What is 15 percent of 240", "36", JUDGE_EXACT, domain="math"),
        BenchProblem("m10", "How many prime numbers between 1 and 10", "4", JUDGE_EXACT, domain="math"),
        # --- code ---
        BenchProblem("c1", "Write a Python function that returns True if a list has duplicates.",
                     "len(set(", JUDGE_CONTAINS, domain="code"),
        BenchProblem("c2", "Write Python to reverse a string without using [::-1]",
                     "reversed", JUDGE_CONTAINS, alternatives=["while", "for"], domain="code"),
        BenchProblem("c3", "Python: check if a string is a palindrome",
                     "==", JUDGE_CONTAINS, alternatives=["reversed"], domain="code"),
        BenchProblem("c4", "Write a Python function returning the nth Fibonacci number",
                     "fibonacci", JUDGE_CONTAINS, domain="code"),
        BenchProblem("c5", "Python: find the maximum element of a list without max()",
                     "for ", JUDGE_CONTAINS, alternatives=[">"], domain="code"),
        # --- research/facts ---
        BenchProblem("r1", "What is the capital of Australia?", "Canberra",
                     JUDGE_CONTAINS, domain="research"),
        BenchProblem("r2", "Speed of light in vacuum (km/s, approx)?", "300000",
                     JUDGE_CONTAINS, alternatives=["299792"], domain="research"),
        BenchProblem("r3", "Who wrote the theory of relativity?", "Einstein",
                     JUDGE_CONTAINS, domain="research"),
        BenchProblem("r4", "Chemical symbol for gold?", "Au", JUDGE_CONTAINS,
                     alternatives=["AU"], domain="research"),
        BenchProblem("r5", "How many bones in the adult human body?", "206",
                     JUDGE_EXACT, domain="research"),
        # --- review / verification ---
        BenchProblem("v1", "Verify: 9 x 8 = 74. Is this correct?", "No", JUDGE_ANY,
                     alternatives=["no", "false", "incorrect", "wrong"], domain="review"),
        BenchProblem("v2", "Is the statement 'the earth is flat' true or false?", "False",
                     JUDGE_ANY, alternatives=["false", "no"], domain="review"),
        # --- creative ---
        BenchProblem("k1", "Brainstorm 3 names for a physics tutoring app", "physics",
                     JUDGE_CONTAINS,
                     domain="creative"),
        BenchProblem("k2", "Give me ideas to reduce energy use at home", "light",
                     JUDGE_ANY, alternatives=["energy", "heat", "power"],
                     domain="creative"),
    ]

    def __init__(self, config: Optional[Config] = None,
                 pattern_lib: Optional[PatternLibrary] = None,
                 memory: Optional[MemorySystem] = None,
                 learn: Optional[LearningSystem] = None,
                 problems: Optional[List[BenchProblem]] = None):
        self.config = config or Config()
        self.pattern_lib = pattern_lib
        self.memory = memory
        self.learn = learn
        self.problems = problems or list(self.DEFAULTS)

    @staticmethod
    def _normalize(s: str) -> str:
        """Strip thousands separators, whitespace, and common noise so
        numerically equal answers match ('1,275' == '1275', '299,792.458'
        == '299792')."""
        s = s.lower()
        s = s.replace(",", "").replace(" ", "").replace("\u00a0", "")
        return s

    def _judge(self, prob: BenchProblem, answer: str) -> bool:
        a = self._normalize(answer.strip())
        e = self._normalize(prob.expected.strip())
        if prob.judge == JUDGE_EXACT:
            return a == e or e in a or a in e
        if prob.judge == JUDGE_CONTAINS:
            alts = prob.alternatives or []
            return any(c.lower() in a for c in [prob.expected] + alts)
        if prob.judge == JUDGE_ANY:
            alts = prob.alternatives or [prob.expected]
            return any(c.lower() in a for c in alts)
        return False

    def run(self, executor: Optional[Executor] = None) -> List[BenchRow]:
        executor = executor or Executor(self.config, pattern_lib=self.pattern_lib)
        rows: List[BenchRow] = []
        for prob in self.problems:
            t0 = time.time()
            try:
                res = executor.execute(prob.problem)
            except Exception:
                res = None
            dur = time.time() - t0
            if res is None or not res.answer.strip():
                rows.append(BenchRow(pid=prob.id, correct=False,
                                     tier="none", pattern=None,
                                     cost_usd=0.0, duration_s=dur, answer="(no answer)"))
                correct = False
            else:
                correct = self._judge(prob, res.answer)
                rows.append(BenchRow(pid=prob.id, correct=correct,
                                     tier=res.tier_used.value,
                                     pattern=(res.notes[0]["pattern"] if res.notes
                                              and res.notes[0].get("event") == "matched"
                                              else None),
                                     cost_usd=res.cost_usd, duration_s=dur,
                                     answer=res.answer[:120]))
            if self.learn:
                self.learn.judge(prob.domain, res.tier_used.value if res else "none", correct)
            if self.memory and res:
                self.memory.record_run(res, correct=correct)
                if not correct:
                    self.learn.postmortem(prob.problem, res.answer,
                                          prob.expected, res.confidence,
                                          res.tier_used.value)
        return rows

    def problem_by_id(self, pid: str) -> Optional[BenchProblem]:
        """Look up the ground-truth problem for a result row id."""
        for prob in self.problems:
            if prob.id == pid:
                return prob
        return None

    def summary(self, rows: List[BenchRow]) -> Dict[str, Any]:
        n = len(rows)
        correct = [r for r in rows if r.correct]
        return {
            "total": n,
            "correct": len(correct),
            "accuracy": round(len(correct) / n, 3) if n else 0.0,
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 6),
            "total_time_s": round(sum(r.duration_s for r in rows), 2),
            "avg_duration_s": round(sum(r.duration_s for r in rows) / n, 2) if n else 0,
        }
