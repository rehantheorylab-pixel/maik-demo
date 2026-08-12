"""Learning systems: ELO per domain, postmortems, contradiction mining.

ELO: every CEO/domain accumulates an ELO-style rating from judged runs —
routing weights shift toward winning domains over time.
Postmortem: after a judged failure, record problem/answer/expected for review.
ContradictionMiner: runs the same problem through two different tiers/models;
when answers disagree, the pair becomes a "contradiction record" that the
flywheel (Phase F) converts into reroute rules.
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_WORD_NORM = re.compile(r"\w+")

_NUM_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "hundred": "100", "thousand": "1000",
}


def _normalize_tokens(ws: List[str]) -> List[str]:
    out = []
    for w in ws:
        if w in _NUM_WORDS:
            out.append(_NUM_WORDS[w])
        else:
            out.append(w)
    return out


class _WordSet:
    def __init__(self, text: str):
        self.words = _normalize_tokens(_WORD_NORM.findall(text.lower()))

    def __or__(self, other: "_WordSet") -> set:
        return set(self.words) | set(other.words)

    def __and__(self, other: "_WordSet") -> set:
        return set(self.words) & set(other.words)

    def __len__(self) -> int:
        return len(self.words)

K_ELO = 16  # update speed — higher = faster learning, more volatility


@dataclass
class EloEntry:
    key: str            # e.g. "domain:math" or "expert:code_writer"
    rating: float = 1200.0
    n_judged: int = 0

    def update(self, won: bool, opponent: float) -> None:
        exp = 1 / (1 + 10 ** ((opponent - self.rating) / 400))
        score = 1.0 if won else 0.0
        self.rating += K_ELO * (score - exp)
        self.n_judged += 1


@dataclass
class Postmortem:
    problem: str
    answer: str
    expected: str
    confidence_at_failure: float
    tier: str
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("problem", "answer", "expected", "confidence_at_failure",
                 "tier", "ts")}


@dataclass
class ContradictionRecord:
    problem: str
    answers: List[str]          # two or more divergent answers
    models: List[str]           # parallel models used
    resolved: Optional[str] = None   # ground truth if known
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("problem", "answers", "models", "resolved", "ts")}


class LearningSystem:
    def __init__(self, base: Optional[Path] = None):
        _env = os.environ.get("MAIK_DATA_DIR", "")
        self.base = base or (Path(_env) / "learn" if _env else
                             Path(__file__).resolve().parent.parent / "learn")
        self.base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()  # reentrant — status() calls rankings()
        self.elo: Dict[str, EloEntry] = {}
        self.postmortems: List[Postmortem] = []
        self.contradictions: List[ContradictionRecord] = []
        self._load()

    # -- persistence -------------------------------------------------------

    def _path(self, name: str) -> Path:
        return self.base / name

    def _load(self) -> None:
        for name, attr, cls in [("elo.json", "elo", EloEntry),
                                ("postmortems.jsonl", "postmortems", Postmortem),
                                ("contradictions.jsonl", "contradictions",
                                 ContradictionRecord)]:
            p = self._path(name)
            if not p.exists():
                continue
            with self._lock:
                raw = p.read_text()
                if name == "elo.json":
                    self.elo = {k: EloEntry(**v) for k, v in
                                json.loads(raw).items()}
                else:
                    setattr(self, attr, [cls(**json.loads(line))
                                         for line in raw.splitlines()
                                         if line.strip()])

    def _save(self, name: str, lines: str) -> None:
        self._path(name).write_text(lines)

    # -- ELO ---------------------------------------------------------------

    def judge(self, domain: str, expert: str, won: bool) -> Tuple[float, float]:
        """Update ELO for domain and expert vs the population mean (1200)."""
        with self._lock:
            d_entry = self.elo.setdefault(f"domain:{domain}", EloEntry(
                key=f"domain:{domain}"))
            e_entry = self.elo.setdefault(f"expert:{expert}", EloEntry(
                key=f"expert:{expert}"))
            mean = 1200.0
            d_entry.update(won, mean)
            e_entry.update(won, mean)
            self._save("elo.json",
                       json.dumps({k: {"key": v.key, "rating": v.rating,
                                       "n_judged": v.n_judged}
                                   for k, v in self.elo.items()}, indent=1))
            return d_entry.rating, e_entry.rating

    def rankings(self) -> Dict[str, float]:
        with self._lock:
            return {k: v.rating for k, v in
                    sorted(self.elo.items(), key=lambda x: -x[1].rating)}

    # -- postmortems -------------------------------------------------------

    def postmortem(self, problem: str, answer: str, expected: str,
                   confidence: float, tier: str) -> None:
        with self._lock:
            self.postmortems.append(Postmortem(
                problem=problem, answer=answer, expected=expected,
                confidence_at_failure=confidence, tier=tier))
            self._save("postmortems.jsonl",
                       "\n".join(json.dumps(p.to_dict())
                                 for p in self.postmortems))

    # -- contradiction mining ----------------------------------------------

    def mine_contradiction(self, problem: str, answers: List[str],
                           models: List[str],
                           resolved: Optional[str] = None) -> Optional[ContradictionRecord]:
        """Record only if answers genuinely diverge (token overlap < 50%)."""
        if len(set(answers)) <= 1:
            return None
        words = [_WORD_NORM.findall(a.lower()) for a in answers]
        sets = [_WordSet(a) for a in answers]
        overlaps = []
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                a, b = sets[i], sets[j]
                union = a | b
                if not union:
                    continue
                overlaps.append(len(a & b) / len(union))
        if overlaps and max(overlaps) >= 0.5:
            return None  # too similar — not a real contradiction
        with self._lock:
            rec = ContradictionRecord(problem=problem, answers=answers,
                                      models=models, resolved=resolved)
            self.contradictions.append(rec)
            self._save("contradictions.jsonl",
                       "\n".join(json.dumps(c.to_dict())
                                 for c in self.contradictions))
            return rec

    def status(self) -> dict:
        with self._lock:
            return {
                "elo_entries": len(self.elo),
                "postmortems": len(self.postmortems),
                "contradictions": len(self.contradictions),
                "top_domains": dict(sorted(self.rankings().items(),
                                           key=lambda x: -x[1])[:5]),
            }
