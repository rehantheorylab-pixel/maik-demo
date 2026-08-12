import time, hashlib, random
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Vote:
    id: str
    topic: str
    options: list[str]
    votes: dict = field(default_factory=dict)
    status: str = "open"
    created_at: float = field(default_factory=time.time)

class VotingManager:
    def __init__(self):
        self._votes: dict[str, Vote] = {}
        self._voter_weights: dict[str, float] = {}

    def create_vote(self, topic: str, options: list[str]) -> str:
        vid = hashlib.md5(f"{topic}:{time.time()}".encode()).hexdigest()[:8]
        self._votes[vid] = Vote(id=vid, topic=topic, options=options)
        return vid

    def cast(self, vote_id: str, voter: str, choice: str) -> bool:
        v = self._votes.get(vote_id)
        if not v or v.status != "open" or choice not in v.options:
            return False
        weight = self._voter_weights.get(voter, 1.0)
        v.votes[voter] = choice
        return True

    def close(self, vote_id: str) -> Optional[dict]:
        v = self._votes.get(vote_id)
        if not v: return None
        v.status = "closed"
        counts = {opt: 0 for opt in v.options}
        weighted = {opt: 0.0 for opt in v.options}
        for voter, choice in v.votes.items():
            w = self._voter_weights.get(voter, 1.0)
            counts[choice] += 1
            weighted[choice] += w
        total_votes = len(v.votes)
        winner = max(weighted, key=weighted.get)
        result = {
            "vote_id": vote_id, "topic": v.topic, "total": total_votes,
            "winner": winner, "counts": counts, "weighted": weighted,
        }
        return result

    def set_weight(self, voter: str, weight: float):
        self._voter_weights[voter] = weight

    def list_open(self) -> list[dict]:
        return [{"id": vid, "topic": v.topic, "options": v.options, "votes": len(v.votes)}
                for vid, v in self._votes.items() if v.status == "open"]

    def results(self, vote_id: str) -> Optional[dict]:
        v = self._votes.get(vote_id)
        if not v: return None
        counts = {opt: sum(1 for c in v.votes.values() if c == opt) for opt in v.options}
        return {"id": vote_id, "topic": v.topic, "status": v.status, "options": v.options, "counts": counts, "total": len(v.votes)}

    def all_votes(self) -> list[dict]:
        return [self.results(vid) for vid in self._votes]

vote_manager = VotingManager()
