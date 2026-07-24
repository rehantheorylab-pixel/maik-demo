import time
import json
import random
import copy
import hashlib
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Genome:
    config: dict = field(default_factory=dict)
    fitness: float = 0.0
    age: int = 0
    id: str = ""

class PBTEngine:
    def __init__(self, population_size: int = 10):
        self._population: list[Genome] = []
        self._population_size = population_size
        self._generation = 0
        self._history: list[dict] = []

    def seed(self, base_config: dict):
        for i in range(self._population_size):
            cfg = copy.deepcopy(base_config)
            cfg = self._mutate(cfg, intensity=0.3)
            self._population.append(Genome(
                config=cfg,
                fitness=random.uniform(0.3, 0.7),
                age=0,
                id=hashlib.md5(f"{time.time()}:{i}".encode()).hexdigest()[:8],
            ))

    def _mutate(self, config: dict, intensity: float = 0.1) -> dict:
        mutated = copy.deepcopy(config)
        for key in mutated:
            if isinstance(mutated[key], (int, float)):
                noise = mutated[key] * intensity * random.uniform(-1, 1)
                if isinstance(mutated[key], int):
                    mutated[key] = max(1, int(mutated[key] + noise))
                else:
                    mutated[key] = max(0.01, mutated[key] + noise)
            if isinstance(mutated[key], str) and random.random() < intensity:
                mutated[key] = mutated[key][::-1] if len(mutated[key]) < 10 else mutated[key]
        return mutated

    def _crossover(self, parent1: dict, parent2: dict) -> dict:
        child = {}
        for key in parent1:
            if key in parent2 and random.random() < 0.5:
                child[key] = copy.deepcopy(parent2[key])
            else:
                child[key] = copy.deepcopy(parent1[key])
        return child

    def evaluate(self, genome_id: str, fitness_delta: float):
        for g in self._population:
            if g.id == genome_id:
                g.fitness = g.fitness * 0.7 + fitness_delta * 0.3
                g.age += 1
                break

    def evolve(self, fraction_keep: float = 0.5) -> int:
        self._population.sort(key=lambda g: -g.fitness)
        keep = max(2, int(len(self._population) * fraction_keep))
        survivors = self._population[:keep]

        children = []
        for i in range(self._population_size - keep):
            p1 = random.choice(survivors)
            p2 = random.choice(survivors)
            child_cfg = self._crossover(p1.config, p2.config)
            child_cfg = self._mutate(child_cfg, intensity=0.1)
            children.append(Genome(
                config=child_cfg,
                fitness=p1.fitness * 0.5 + p2.fitness * 0.5,
                age=0,
                id=hashlib.md5(f"{time.time()}:child{i}".encode()).hexdigest()[:8],
            ))

        self._history.append({
            "generation": self._generation,
            "survivors": keep,
            "children": len(children),
            "best_fitness": survivors[0].fitness if survivors else 0,
        })
        self._population = survivors + children
        self._generation += 1
        return self._generation

    def best_config(self) -> dict:
        if not self._population:
            return {}
        best = max(self._population, key=lambda g: g.fitness)
        return best.config

    def stats(self) -> dict:
        if not self._population:
            return {"generation": self._generation, "size": 0}
        return {
            "generation": self._generation,
            "population": len(self._population),
            "best_fitness": max(g.fitness for g in self._population),
            "avg_fitness": sum(g.fitness for g in self._population) / len(self._population),
            "history_length": len(self._history),
        }

class RewardShaper:
    def __init__(self):
        self._difficulty_map: dict[str, float] = {}

    def record(self, problem_type: str, success: bool, agents_used: int):
        base = self._difficulty_map.get(problem_type, 0.5)
        factor = 1.0 + (agents_used / 10.0)
        delta = 0.05 * factor if success else -0.03
        self._difficulty_map[problem_type] = max(0.01, min(1.0, base + delta))

    def difficulty(self, problem_type: str) -> float:
        return self._difficulty_map.get(problem_type, 0.5)

    def shaped_reward(self, base_confidence: float, problem_type: str, agents_used: int) -> float:
        diff = self.difficulty(problem_type)
        difficulty_bonus = diff * 0.2
        agent_penalty = max(0, agents_used - 3) * 0.05
        return max(0.01, min(1.0, base_confidence + difficulty_bonus - agent_penalty))

pbt = PBTEngine()
reward_shaper = RewardShaper()
