import time
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

class IncubationEngine:
    def __init__(self):
        self._ideas: list[dict] = []
        self._hatched: list[dict] = []

    def seed(self, agent_id: str, idea: str, source: str = "", tags: Optional[list[str]] = None):
        entry = {
            "id": hashlib.md5(f"{time.time()}:{idea}".encode()).hexdigest()[:8],
            "agent": agent_id, "idea": idea, "source": source,
            "tags": tags or [], "created_at": time.time(),
            "heat": 0.0, "percolation_count": 0,
        }
        self._ideas.append(entry)

    def percolate(self) -> int:
        now = time.time()
        count = 0
        for idea in self._ideas:
            age = now - idea["created_at"]
            heat = min(1.0, age / 3600.0)
            old_heat = idea["heat"]
            idea["heat"] = heat
            if old_heat < 0.3 and heat >= 0.3:
                idea["percolation_count"] += 1
            if heat >= 0.8 and old_heat < 0.8:
                self._hatched.append({**idea, "hatched_at": now})
                count += 1
        self._ideas = [i for i in self._ideas if i["heat"] < 0.8]
        return count

    def hatch_one(self) -> Optional[dict]:
        if self._hatched:
            return self._hatched.pop(0)
        return None

    def hot_ideas(self, min_heat: float = 0.3) -> list[dict]:
        return [i for i in self._ideas if i["heat"] >= min_heat]

class AbductiveReasoner:
    def __init__(self):
        self._patterns: list[dict] = []

    def record_pattern(self, observation: str, explanation: str, confidence: float = 0.5):
        self._patterns.append({
            "observation": observation, "explanation": explanation,
            "confidence": confidence, "recorded_at": time.time(),
        })

    def best_explanation(self, observation: str, top_k: int = 3) -> list[dict]:
        obset = set(observation.lower().split())
        scored = []
        for p in self._patterns:
            poset = set(p["observation"].lower().split())
            sim = len(obset & poset) / max(len(obset | poset), 1)
            scored.append((sim * p["confidence"], p))
        scored.sort(key=lambda x: -x[0])
        return [{"explanation": s[1]["explanation"], "confidence": s[1]["confidence"], "score": s[0]} for s in scored[:top_k]]

class AnalogicalMapper:
    def __init__(self):
        self._mappings: list[dict] = []

    def record_mapping(self, source: str, target: str, relation: str, confidence: float = 0.5):
        self._mappings.append({
            "source": source, "target": target, "relation": relation,
            "confidence": confidence, "recorded_at": time.time(),
        })

    def find_analogies(self, problem: str, top_k: int = 3) -> list[dict]:
        pset = set(problem.lower().split())
        scored = []
        for m in self._mappings:
            sset = set(m["source"].lower().split())
            tset = set(m["target"].lower().split())
            sim = max(len(pset & sset) / max(len(pset | sset), 1), len(pset & tset) / max(len(pset | tset), 1))
            scored.append((sim * m["confidence"], m))
        scored.sort(key=lambda x: -x[0])
        return [
            {"source": s[1]["source"], "target": s[1]["target"],
             "relation": s[1]["relation"], "score": s[0]}
            for s in scored[:top_k]
        ]

class WanderingThoughts:
    def __init__(self, seed_ideas: Optional[list[str]] = None):
        self._associations: dict[str, list[str]] = {}
        if seed_ideas:
            for idea in seed_ideas:
                self._associations[idea] = []

    def add_association(self, from_idea: str, to_idea: str):
        self._associations.setdefault(from_idea, []).append(to_idea)

    def wander(self, start: str, steps: int = 3) -> list[str]:
        path = [start]
        current = start
        for _ in range(steps):
            neighbors = self._associations.get(current, [])
            if not neighbors:
                break
            current = random.choice(neighbors)
            path.append(current)
        return path

    def random_spark(self, pool: list[str]) -> str:
        return random.choice(pool) if pool else ""

class HierarchicalChunker:
    def chunk(self, text: str, max_chunk_size: int = 200) -> list[str]:
        sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
        chunks, current = [], []
        size = 0
        for s in sentences:
            if size + len(s) > max_chunk_size and current:
                chunks.append(". ".join(current) + ".")
                current, size = [s], len(s)
            else:
                current.append(s)
                size += len(s)
        if current:
            chunks.append(". ".join(current) + ".")
        return chunks

class TrainingPipeline:
    def __init__(self):
        self._gold_repos: list[dict] = []
        self._distillation_log: list[dict] = []
        self._pattern_db: dict[str, list[str]] = {}

    def add_gold(self, name: str, content: str, domain: str = "general") -> str:
        gid = hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:8]
        self._gold_repos.append({"id": gid, "name": name, "content": content[:500], "domain": domain, "added": time.time()})
        return gid

    def remove_gold(self, gold_id: str) -> bool:
        for i, g in enumerate(self._gold_repos):
            if g["id"] == gold_id:
                self._gold_repos.pop(i)
                return True
        return False

    def distill(self, source_model: str, target_model: str, data: str) -> dict:
        entry = {"source": source_model, "target": target_model, "data": data[:100], "timestamp": time.time()}
        self._distillation_log.append(entry)
        return {"status": "distilled", "source": source_model, "target": target_model, "size": len(data)}

    def store_pattern(self, key: str, pattern: str):
        self._pattern_db.setdefault(key, []).append(pattern)

    def get_patterns(self, key: str) -> list[str]:
        return self._pattern_db.get(key, [])

    def gold_stats(self) -> dict:
        return {"total_gold": len(self._gold_repos), "total_distillations": len(self._distillation_log),
                "total_patterns": sum(len(v) for v in self._pattern_db.values()),
                "domains": list(set(g["domain"] for g in self._gold_repos))}

    def list_gold(self) -> list[dict]:
        return [{"id": g["id"], "name": g["name"], "domain": g["domain"], "content": g["content"][:80]} for g in self._gold_repos]

incubation = IncubationEngine()
abductor = AbductiveReasoner()
analogizer = AnalogicalMapper()
wanderer = WanderingThoughts(["code", "math", "creative", "design", "security", "data", "test", "deploy"])
chunker = HierarchicalChunker()
training = TrainingPipeline()
