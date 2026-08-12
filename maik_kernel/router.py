"""CEO-aware routing with a persistent pattern cache (upgrade U5).

Design: rule-based ProblemClassifier first (instant, free) with a confidence
score from rule-match strength. Decisions are cached by a *normalized bucket*
(problem_type + expert + difficulty) so similar problems hit the cache.
The cache persists to SQLite and becomes the seed corpus for the
pattern_library (Phase D).
"""

import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import CEOProfile, Config, ModelTier

RULES: List[Tuple[str, str, str, float]] = [
    # (regex, domain, expert, base_confidence)
    # Code-writing intent beats numeric keywords ("prime"/"\d+") found inside code problems.
    (r"code|program|function|bug|implement|debug|\bdef \w+|\bclass \w+|\.py\b|\.rs\b|refactor|compile", "code", "code_writer", 0.92),
    (r"calculat|solve|equation|integral|derivative|\b\d+\s*[\+\-\*/\^]\s*\d+|prime|factorial", "math", "math_solver", 0.9),
    (r"research|explain|what is|who is|history of|compare|analyze|paper|study", "research", "explorer", 0.8),
    (r"security|vulnerab|exploit|audit|hack|encrypt|inject|vuln", "security", "security_auditor", 0.85),
    (r"design|creative|write a story|poem|brainstorm|name|idea", "creative", "brainstormer", 0.7),
    (r"plan|schedule|steps|roadmap|how do i (start|begin)", "planning", "scheduler", 0.75),
    (r"data|chart|graph|plot|statistics|csv|dataset", "data", "analyst", 0.8),
    (r"summarize|synthesiz|integrate|review|critic|check", "review", "verifier", 0.75),
]

DEFAULT_DOMAIN, DEFAULT_EXPERT = "strategy", "planner"


def _difficulty_bucket(text: str) -> str:
    """Tiny heuristic difficulty: short = easy, long = hard."""
    n = len(text.split())
    if n <= 8:
        return "easy"
    if n <= 40:
        return "medium"
    return "hard"


def _bucket_key(problem_type: str, expert: str, difficulty: str) -> str:
    return f"{problem_type}|{expert}|{difficulty}"


@dataclass
class RoutingDecision:
    ceo_domain: str
    ceo_name: str
    expert: str
    tier: ModelTier
    problem_type: str
    difficulty: str
    confidence: float
    explanation: str
    cached: bool

    def to_dict(self) -> dict:
        return {
            "domain": self.ceo_domain, "ceo": self.ceo_name, "expert": self.expert,
            "model_tier": self.tier.value, "problem_type": self.problem_type,
            "difficulty": self.difficulty, "confidence": round(self.confidence, 3),
            "explanation": self.explanation, "cached": self.cached,
        }


class ProblemClassifier:
    def classify(self, problem: str) -> Tuple[str, str, float]:
        """Return (domain, expert, confidence). Rule strength sets confidence.

        Two signals are combined: rule strength AND intent explicitness. A
        code-writing intent ("write a function") outranks a weaker incidental
        keyword match ("prime", digits) even when its raw conf is similar.
        """
        text = problem.lower()
        best: Optional[Tuple[str, str, float]] = None
        for pat, domain, expert, conf in RULES:
            if re.search(pat, text):
                if best is None or conf > best[2] + 1e-9:
                    best = (domain, expert, conf)
        if best is None:
            return DEFAULT_DOMAIN, DEFAULT_EXPERT, 0.5
        # word-count modulation: longer problems slightly harder to route
        conf = max(0.3, best[2] - min(0.15, len(problem.split()) / 400))
        # explicit code-writing intent outranks incidental keyword matches
        if best[0] != "code" and re.search(r"code|program|function|def \w+|class \w+|\.py\b", text):
            if re.search(RULES[0][0], text):
                return ("code", "code_writer", max(conf, 0.88))
        return best[0], best[1], conf


class PatternCache:
    """In-memory + SQLite-persistent decision cache with decay and perf curves."""

    def __init__(self, path: Path, decay_days: int = 30):
        self.path = path
        self.decay_days = decay_days
        self._mem: Dict[str, dict] = {}
        self.stats = {"hits": 0, "misses": 0}
        self._curves: Dict[str, Dict[str, int]] = {}  # bucket -> {success, total}
        self._init_db()

    def _init_db(self) -> None:
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS patterns "
            "(bucket TEXT PRIMARY KEY, decision TEXT, ts REAL)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS curves "
            "(bucket TEXT, success INT, total INT, PRIMARY KEY (bucket))")
        self._db.commit()
        self._load()

    def _load(self) -> None:
        for bucket, decision, ts in self._db.execute(
                "SELECT bucket, decision, ts FROM patterns"):
            self._mem[bucket] = {"decision": json.loads(decision), "ts": ts}
        for bucket, s, t in self._db.execute(
                "SELECT bucket, success, total FROM curves"):
            self._curves[bucket] = {"success": s, "total": t}

    def get(self, bucket: str) -> Optional[dict]:
        """Cache hit logic: present + not decayed out."""
        entry = self._mem.get(bucket)
        if entry is None:
            self.stats["misses"] += 1
            return None
        age_days = (time.time() - entry["ts"]) / 86400
        if age_days > self.decay_days:
            del self._mem[bucket]
            self._db.execute("DELETE FROM patterns WHERE bucket=?", (bucket,))
            self._db.commit()
            self.stats["misses"] += 1
            return None
        self.stats["hits"] += 1
        d = entry["decision"]
        d["cached"] = True
        return d

    def put(self, bucket: str, decision: RoutingDecision) -> None:
        d = {k: v for k, v in decision.to_dict().items() if k != "cached"}
        d["cached"] = False
        with threading.Lock():  # simple write lock
            self._mem[bucket] = {"decision": d, "ts": time.time()}
            self._db.execute(
                "INSERT OR REPLACE INTO patterns VALUES (?,?,?)",
                (bucket, json.dumps(d), time.time()))
            self._db.commit()
        self.stats["misses"] += 1  # first store counts as a miss-then-learn

    def record_outcome(self, bucket: str, success: bool) -> None:
        c = self._curves.setdefault(bucket, {"success": 0, "total": 0})
        c["success"] += 1 if success else 0
        c["total"] += 1
        self._db.execute(
            "INSERT OR REPLACE INTO curves VALUES (?,?,?)",
            (bucket, c["success"], c["total"]))
        self._db.commit()

    def success_rate(self, bucket: str) -> Optional[float]:
        c = self._curves.get(bucket)
        if not c or c["total"] == 0:
            return None
        return c["success"] / c["total"]

    @property
    def hit_rate(self) -> float:
        tot = self.stats["hits"] + self.stats["misses"]
        return self.stats["hits"] / tot if tot else 0.0

    def close(self) -> None:
        self._db.close()


class Router:
    """Problem -> RoutingDecision. Respects config friction dial."""

    def __init__(self, config: Config, cache_path: Optional[Path] = None):
        self.config = config
        self.classifier = ProblemClassifier()
        self.cache = PatternCache(
            cache_path or (Path(__file__).resolve().parent.parent / "pattern_cache.db"))

    def route(self, problem: str) -> RoutingDecision:
        ptype, expert, conf = self.classifier.classify(problem)
        difficulty = _difficulty_bucket(problem)
        bucket = _bucket_key(ptype, expert, difficulty)

        # cache hit: restore the stored decision, bump confidence by curve
        stored = self.cache.get(bucket)
        if stored is not None:
            rate = self.cache.success_rate(bucket)
            conf = max(stored["confidence"], (rate or 0.5) if rate is not None else conf)
            return RoutingDecision(
                ceo_domain=stored["domain"], ceo_name=stored["ceo"],
                expert=stored["expert"], tier=ModelTier(stored["model_tier"]),
                problem_type=ptype, difficulty=difficulty,
                confidence=min(1.0, conf),
                explanation=stored["explanation"] + " (cached pattern)",
                cached=True)

        ceo = self.config.ceo_for_domain(ptype) or self.config.ceos[0]
        # friction dial gates: at high dial, below-threshold problems are
        # flagged rather than silently boosted — the caller sees conf < dial
        # threshold and treats it as "needs verification"
        decision = RoutingDecision(
            ceo_domain=ceo.domain, ceo_name=ceo.name, expert=expert,
            tier=ceo.default_tier, problem_type=ptype, difficulty=difficulty,
            confidence=conf,
            explanation=f"CEO '{ceo.name}' assigned, classified as {ptype}, "
                        f"routed to {expert} on {ceo.default_tier.value} tier",
            cached=False)
        self.cache.put(bucket, decision)
        return decision

    def close(self) -> None:
        self.cache.close()
