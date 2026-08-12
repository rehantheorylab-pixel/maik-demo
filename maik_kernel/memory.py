"""L1/L2/L3 memory + thought vector store.

Kept structure from maik-demo v2 (audit-verified), made testable and real:
  L1 = working memory      (current problem context, volatile)
  L2 = episodic memory     (past runs: problem, answer, outcome, cost)
  L3 = semantic memory     (durable facts/insights distilled from L2)
ThoughtVDB = lightweight tf-idf similarity store over thoughts (no GPU needed;
  upgradeable to real embeddings later — same public API).
"""

import json
import math
import os
import re
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .executor import ExecutionResult


class _TfIdf:
    """Minimal tf-idf over a document corpus — enough for local retrieval."""

    def __init__(self):
        self.docs: List[str] = []
        self._idf: Dict[str, float] = {}

    def add(self, doc: str) -> None:
        self.docs.append(doc)
        self._rebuild()

    def _tok(self, s: str) -> List[str]:
        return re.findall(r"\w+", s.lower())

    def _rebuild(self) -> None:
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(self._tok(d)))
        n = len(self.docs) or 1
        self._idf = {t: math.log(n / c) + 1 for t, c in df.items()}

    def top(self, query: str, k: int = 3) -> List[Tuple[int, float]]:
        if not self.docs:
            return []
        qv = self._vec(self._tok(query))
        scored = []
        for i, d in enumerate(self.docs):
            tv = self._vec(self._tok(d))
            scored.append((i, _cos(qv, tv)))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def _vec(self, toks: List[str]) -> Dict[str, float]:
        tf = Counter(toks)
        norm = math.sqrt(sum((c * self._idf.get(t, 0)) ** 2 for t, c in tf.items())) or 1
        return {t: c * self._idf.get(t, 0) / norm for t, c in tf.items()}


def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    ks = set(a) & set(b)
    if not ks:
        return 0.0
    va = [a[k] for k in ks]
    vb = [b[k] for k in ks]
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class Episode:
    problem: str
    answer: str
    confidence: float
    cost_usd: float
    tier: str
    correct: Optional[bool] = None   # set by ground-truth comparison (Phase E)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "problem": self.problem, "answer": self.answer,
            "confidence": self.confidence, "correct": self.correct,
            "cost_usd": self.cost_usd, "tier": self.tier, "ts": self.ts,
        }


class L1Memory:
    """Working memory — current problem context."""

    def __init__(self):
        self.ctx: Dict[str, Any] = {}
        self.clear()

    def clear(self) -> None:
        self.ctx = {"start_ts": time.time()}

    def set(self, k: str, v: Any) -> None:
        self.ctx[k] = v

    def get(self, k: str) -> Any:
        return self.ctx.get(k)


class L2Memory:
    """Episodic memory — persisted history of runs."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.episodes: List[Episode] = []
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.load()

    def record(self, res: ExecutionResult, correct: Optional[bool] = None) -> Episode:
        ep = Episode(problem=res.problem, answer=res.answer,
                     confidence=res.confidence, correct=correct,
                     cost_usd=res.cost_usd, tier=(res.tier_used.value if hasattr(res, "tier_used") else "flash"))
        with self._lock:
            self.episodes.append(ep)
            if self.path:
                self._append(ep)
        return ep

    def _append(self, ep: Episode) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(ep.to_dict()) + "\n")

    def load(self) -> None:
        with self._lock:
            out = []
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if line:
                    out.append(Episode(**json.loads(line)))
            self.episodes = out

    def recent(self, n: int = 10) -> List[Episode]:
        return list(self.episodes[-n:])

    def accuracy(self) -> Optional[float]:
        judged = [e for e in self.episodes if e.correct is not None]
        if not judged:
            return None
        return sum(1 for e in judged if e.correct) / len(judged)

    def total_cost(self) -> float:
        return sum(e.cost_usd for e in self.episodes)


class L3Memory:
    """Semantic memory — durable insights distilled from episodes."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.facts: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.facts = json.loads(self.path.read_text())

    def distill(self, episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Simple distillation: recurring problem patterns + recurring answer
        fragments become durable facts. Replaceable by an LLM-summarizer later
        (same API)."""
        new_facts = []
        for ep in episodes:
            sig = re.sub(r"\d+", "<NUM>", ep.problem.lower())[:60]
            dup = any(f["sig"] == sig for f in self.facts)
            if not dup:
                fact = {"sig": sig, "insight": f"Answered '{ep.problem[:60]}' with "
                        f"confidence {ep.confidence:.2f} on {ep.tier}",
                        "ts": time.time()}
                new_facts.append(fact)
        with self._lock:
            self.facts.extend(new_facts)
            if self.path:
                self.path.write_text(json.dumps(self.facts, indent=1))
        return new_facts


class ThoughtVDB:
    """Vector store over thoughts/answers — tf-idf now, embeddings-ready."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self._tfidf = _TfIdf()
        self._texts: List[str] = []
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.load()

    def add(self, text: str) -> None:
        with self._lock:
            self._tfidf.add(text)
            self._texts.append(text)

    def search(self, query: str, k: int = 3) -> List[Tuple[str, float]]:
        with self._lock:
            return [(self._texts[i], s) for i, s in self._tfidf.top(query, k)]

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self._texts))

    def load(self) -> None:
        texts = json.loads(self.path.read_text())
        for t in texts:
            self._texts.append(t)
            self._tfidf.add(t)


class MemorySystem:
    """Facade: L1 (working) + L2 (episodes) + L3 (insights) + thought VDB."""

    def __init__(self, base: Optional[Path] = None):
        _env = os.environ.get("MAIK_DATA_DIR", "")
        base = base or (Path(_env) / "memory" if _env else
                        Path(__file__).resolve().parent.parent / "memory")
        base.mkdir(parents=True, exist_ok=True)
        self.l1 = L1Memory()
        self.l2 = L2Memory(base / "episodes.jsonl")
        self.l3 = L3Memory(base / "facts.json")
        self.thoughts = ThoughtVDB(base / "thoughts.json")

    def record_run(self, res: ExecutionResult, correct: Optional[bool] = None) -> None:
        ep = self.l2.record(res, correct)
        self.thoughts.add(f"{res.problem} :: {res.answer}")
        self.l3.distill([ep])
        self.thoughts.save()

    def status(self) -> dict:
        return {
            "episodes": len(self.l2.episodes),
            "accuracy": self.l2.accuracy(),
            "total_cost_usd": round(self.l2.total_cost(), 6),
            "facts": len(self.l3.facts),
            "thought_vectors": len(self.thoughts._texts),
        }
