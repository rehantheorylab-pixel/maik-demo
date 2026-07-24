import copy
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TokenBudget:
    total: int = 100_000
    used: int = 0
    per_agent: int = 10_000
    warning_pct: float = 0.15
    critical_pct: float = 0.05

    @property
    def remaining(self) -> int:
        return self.total - self.used

    @property
    def remaining_pct(self) -> float:
        return self.remaining / self.total if self.total > 0 else 0.0

    def can_afford(self, estimated: int) -> bool:
        return self.remaining >= estimated

    def spend(self, amount: int):
        self.used += amount

    def enough_for_full_run(self) -> bool:
        return self.remaining_pct > self.warning_pct

    def enough_for_minimal_run(self) -> bool:
        return self.remaining_pct > self.critical_pct

    def __str__(self) -> str:
        return f"{self.remaining:,}/{self.total:,} tokens left ({self.remaining_pct*100:.0f}%)"

    def mode(self) -> str:
        if self.remaining_pct > self.warning_pct:
            return "normal"
        elif self.remaining_pct > self.critical_pct:
            return "economy"
        return "survival"

@dataclass
class MAIKConfig:
    max_depth: int = 5
    max_parallel: int = 7
    min_confidence: float = 0.6
    agent_timeout_s: int = 60
    friction_dial: int = 5
    predictive_prune_threshold: float = 0.3
    recursion_threshold: int = 2

    @property
    def model_chain(self) -> list[dict]:
        return [
            {"name": "flash", "model": "gemini/gemini-2.0-flash-001", "cost": 0.0001, "roles": ["route","explore","classify","creative"]},
            {"name": "small", "model": "openrouter/qwen/qwen-2.5-coder-3b-instruct", "cost": 0.0003, "roles": ["decompose","review_simple","fact_check"]},
            {"name": "medium", "model": "openrouter/anthropic/claude-3-haiku", "cost": 0.0008, "roles": ["execute","review","plan"]},
            {"name": "large", "model": "openrouter/openai/gpt-4o-mini", "cost": 0.0015, "roles": ["synthesize","verify","security"]},
        ]

    def pick_model(self, role: str, mode: str = "normal") -> dict:
        role_map = {r: i for i, m in enumerate(self.model_chain) for r in m["roles"]}
        idx = role_map.get(role, 1)
        if mode == "survival":
            idx = 0
        elif mode == "economy":
            idx = min(idx, 1)
        return self.model_chain[min(idx, len(self.model_chain)-1)]

@dataclass
class CEOProfile:
    id: str
    name: str
    domains: list
    api_prefixes: list
    min_managers: int = 3
    max_depth: int = 4
    budget_percent: float = 0.1
    model_preference: str = "medium"

CEO_FULL = [
    CEOProfile("ceo-code", "Code & Engineering", ["code","programming","software","engineering","api","backend","frontend"],
               ["/v1/route","/v1/execute","/v1/expert"], 4, 5, 0.15, "medium"),
    CEOProfile("ceo-data", "Data & Learning", ["data","learning","ml","ai","training","dataset","model"],
               ["/v1/learn","/v1/evolution"], 3, 4, 0.12, "large"),
    CEOProfile("ceo-knowledge", "Knowledge & Memory", ["knowledge","memory","fact","recall","archive","information"],
               ["/v1/memory","/v1/cognitive/abduce"], 3, 4, 0.10, "medium"),
    CEOProfile("ceo-safety", "Safety & Compliance", ["safety","security","compliance","audit","purity","policy","ethics"],
               ["/v1/safety","/v1/purity"], 3, 4, 0.10, "large"),
    CEOProfile("ceo-cognition", "Cognition & Research", ["cognition","reasoning","logic","boolean","analogy","thinking","research"],
               ["/v1/cognitive","/v1/boolean"], 3, 5, 0.10, "medium"),
    CEOProfile("ceo-corporate", "Corporate & Meta", ["corporate","meta","management","governance","library","organization"],
               ["/v1/library","/v1/meta"], 3, 4, 0.08, "small"),
    CEOProfile("ceo-ops", "Operations", ["operations","schedule","monitor","stats","info","health","infrastructure"],
               ["/v1/schedule","/v1/stats","/v1/info","/v1/cache"], 2, 3, 0.07, "flash"),
    CEOProfile("ceo-creative", "Creative & Design", ["creative","design","ui","ux","art","writing","content","story"],
               ["/v1/route?creative","/v1/execute?creative"], 3, 4, 0.08, "flash"),
    CEOProfile("ceo-security", "Security & Audit", ["security","audit","vulnerability","threat","pentest","cve"],
               ["/v1/route?security","/v1/purity"], 3, 4, 0.07, "large"),
    CEOProfile("ceo-research", "Deep Research", ["research","explore","investigate","analyze","deep","scientific"],
               ["/v1/cognitive/abduce","/v1/cognitive/analogize","/v1/execute?research"], 3, 5, 0.06, "large"),
    CEOProfile("ceo-infra", "Infrastructure", ["infrastructure","deploy","devops","ci","cd","cloud","kubernetes","docker"],
               ["/v1/schedule","/v1/expert/call"], 2, 3, 0.04, "flash"),
    CEOProfile("ceo-product", "Product Management", ["product","management","strategy","roadmap","feature","backlog","sprint"],
               ["/v1/route?planning","/v1/execute?planning"], 2, 3, 0.03, "small"),
]

CEO_LIGHT = [
    CEOProfile("ceo-core", "Core Intelligence", ["code","planning","math","logic","reasoning","general","learning","stats"],
               ["/v1/route","/v1/execute","/v1/learn","/v1/stats","/v1/info","/v1/boolean","/v1/cache"], 2, 4, 0.60, "medium"),
    CEOProfile("ceo-support", "Support & Safety", ["safety","memory","schedule","purity","cognitive","knowledge","corporate","meta"],
               ["/v1/safety","/v1/memory","/v1/schedule","/v1/purity","/v1/cognitive","/v1/library","/v1/meta"], 2, 3, 0.40, "flash"),
]

@dataclass
class ExecutiveCouncil:
    profile: str = "full"
    _ceos: list = field(default_factory=list)
    _api_map: dict = field(default_factory=dict)
    _ceo_budgets: dict = field(default_factory=dict)
    _global_budget: Optional[TokenBudget] = None
    _lock: bool = False

    def __post_init__(self):
        self.configure(self.profile)

    def configure(self, profile: str, global_total: int = 1_000_000):
        self.profile = profile
        self._global_budget = TokenBudget(total=global_total)
        if profile == "full":
            source = CEO_FULL
        else:
            source = CEO_LIGHT
        self._ceos = [copy.deepcopy(c) for c in source]
        self._api_map = {}
        for ceo in self._ceos:
            budget = TokenBudget(total=int(global_total * ceo.budget_percent))
            self._ceo_budgets[ceo.id] = budget
            for prefix in ceo.api_prefixes:
                self._api_map[prefix] = ceo.id

    @property
    def num_ceos(self) -> int:
        return len(self._ceos)

    @property
    def ceo_list(self) -> list:
        return self._ceos

    def ceo_for_api(self, api_path: str) -> Optional[str]:
        sorted_prefixes = sorted(self._api_map.keys(), key=len, reverse=True)
        for prefix in sorted_prefixes:
            if api_path.startswith(prefix):
                return self._api_map[prefix]
        return None

    def ceo_for_domain(self, domain: str) -> CEOProfile:
        d = domain.lower()
        scored = []
        for ceo in self._ceos:
            score = sum(2 for dom in ceo.domains if dom in d)
            if ceo.id.replace("ceo-","") in d:
                score += 5
            scored.append((score, ceo))
        scored.sort(key=lambda x: -x[0])
        return scored[0][1] if scored else self._ceos[0]

    def ceo_by_id(self, ceo_id: str) -> Optional[CEOProfile]:
        for ceo in self._ceos:
            if ceo.id == ceo_id:
                return ceo
        return None

    def budget_for(self, ceo_id: str) -> TokenBudget:
        return self._ceo_budgets.get(ceo_id, self._global_budget or TokenBudget())

    def list_ceos(self) -> list[dict]:
        return [{"id": c.id, "name": c.name, "domains": c.domains[:3],
                 "api_count": len(c.api_prefixes), "managers": c.min_managers,
                 "budget": str(self._ceo_budgets.get(c.id, TokenBudget()))}
                for c in self._ceos]

@dataclass
class Corporate:
    executives: list = field(default_factory=lambda: [
        "Strategy", "Engineering", "Quality", "Research", "Operations",
        "Creative", "Data", "Security", "Infrastructure", "Product"])

    def role_at_depth(self, d: int) -> str:
        if d == 0:
            return "CEO"
        if d == 1:
            idx = min(d - 1, len(self.executives) - 1)
            return f"Exec({self.executives[idx]})"
        if d == 2:
            return "Manager"
        return "Specialist"

    def permission_tier(self, d: int, action: str) -> int:
        high = ("modify_safety","deploy","modify_budget")
        med = ("approve","spawn_agent","access_notes")
        if action in high:
            return 3
        if d <= 1 and action in med:
            return 2
        if action == "execute":
            return 0
        return 1

@dataclass
class ExpertManifest:
    experts: dict = field(default_factory=lambda: {
        "code_writer": {"model":"medium","domains":["code","programming","software"],"desc":"Writes code"},
        "code_reviewer": {"model":"medium","domains":["code","programming","review"],"desc":"Reviews code"},
        "math_solver": {"model":"medium","domains":["math","algebra","calculus","stats"],"desc":"Solves math"},
        "planner": {"model":"small","domains":["planning","strategy","design"],"desc":"Plans steps"},
        "explorer": {"model":"flash","domains":["research","explore","creative"],"desc":"Explores ideas"},
        "synthesizer": {"model":"large","domains":["merge","synthesize","final"],"desc":"Merges outputs"},
        "verifier": {"model":"medium","domains":["verify","test","validate"],"desc":"Verifies solution"},
        "security_auditor": {"model":"large","domains":["security","audit","safety"],"desc":"Security audit"},
    })

    def find_expert(self, domain: str, problem: str = "") -> str:
        best, best_score = "synthesizer", 0
        d, p = domain.lower(), problem.lower()
        for name, info in self.experts.items():
            score = 0
            if name in p:
                score += 3
            for x in info["domains"]:
                if x in d:
                    score += 2
            if score > best_score:
                best, best_score = name, score
        return best

@dataclass
class SafetyConfig:
    circuit_breaker_threshold: int = 3
    cooldown_s: float = 60.0
    triad_required: int = 3
    auto_pause_on_red: bool = True
    kill_file_path: str = "KILL_MAIK"

@dataclass
class MemoryConfig:
    l1_capacity: int = 50
    l1_ttl_s: float = 300.0
    l2_min_confidence: float = 0.7
    l2_min_access: int = 3
    l2_consolidation_interval: float = 600.0
    thought_vdb_max: int = 200

@dataclass
class CognitiveConfig:
    incubation_heat_rate: float = 0.1
    incubation_max_ideas: int = 100
    wander_steps: int = 3
    analogical_top_k: int = 3

@dataclass
class EvolutionConfig:
    population_size: int = 10
    fraction_keep: float = 0.5
    mutation_intensity: float = 0.1

cfg = MAIKConfig()
safety_cfg = SafetyConfig()
memory_cfg = MemoryConfig()
cognitive_cfg = CognitiveConfig()
evolution_cfg = EvolutionConfig()
corp = Corporate()
experts = ExpertManifest()
council = ExecutiveCouncil(profile="full")
