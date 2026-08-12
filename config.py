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
class APIConfig:
    id: str
    provider: str
    model: str
    key_prefix: str = ""
    enabled: bool = True

    def display(self) -> str:
        return f"{self.provider}/{self.model}"

DEFAULT_APIS = [
    APIConfig("api-1", "gemini", "gemini-2.0-flash-001", "AIza"),
    APIConfig("api-2", "openrouter", "qwen/qwen-2.5-coder-3b-instruct", "sk-or"),
    APIConfig("api-3", "openrouter", "anthropic/claude-3-haiku", "sk-or"),
    APIConfig("api-4", "openrouter", "openai/gpt-4o-mini", "sk-or"),
]

@dataclass
class ExecutiveCouncil:
    profile: str = "full"
    _ceos: list = field(default_factory=list)
    _api_map: dict = field(default_factory=dict)
    _ceo_budgets: dict = field(default_factory=dict)
    _global_budget: Optional[TokenBudget] = None
    _lock: bool = False
    _custom_ceo_count: int = 0
    _in_custom_mode: bool = False

    def __post_init__(self):
        self.configure(self.profile)

    def configure(self, profile: str, global_total: int = 1_000_000):
        self.profile = profile
        self._in_custom_mode = False
        self._custom_ceo_count = 0
        self._global_budget = TokenBudget(total=global_total)
        if profile == "full":
            source = CEO_FULL
        elif profile == "light":
            source = CEO_LIGHT
        else:
            try:
                n = int(profile)
                source = CEO_FULL[:n]
                self._in_custom_mode = True
                self._custom_ceo_count = n
            except:
                source = CEO_FULL
        self._ceos = [copy.deepcopy(c) for c in source]
        self._rebuild_maps()

    def configure_custom(self, num_ceos: int, global_total: int = 1_000_000):
        self._in_custom_mode = True
        self._custom_ceo_count = num_ceos
        self.profile = f"custom-{num_ceos}"
        self._global_budget = TokenBudget(total=global_total)
        self._ceos = [copy.deepcopy(c) for c in CEO_FULL[:min(num_ceos, len(CEO_FULL))]]
        extra = num_ceos - len(CEO_FULL)
        for i in range(extra):
            pid = f"ceo-custom-{i+1}"
            c = CEOProfile(pid, f"Custom CEO {i+1}",
                           ["general","custom","ai","automation"],
                           ["/v1/route","/v1/execute"], 2, 3, 0.05, "flash")
            self._ceos.append(c)
        self._rebuild_maps()

    def _rebuild_maps(self):
        self._api_map = {}
        for ceo in self._ceos:
            budget = TokenBudget(total=int(self._global_budget.total * ceo.budget_percent) if self._global_budget else 100000)
            self._ceo_budgets[ceo.id] = budget
            for prefix in ceo.api_prefixes:
                self._api_map[prefix] = ceo.id

    def add_ceo(self, name: str = "", domains: list = None) -> CEOProfile:
        idx = len(self._ceos) + 1
        cid = f"ceo-{name.lower().replace(' ','-')}" if name else f"ceo-custom-{idx}"
        new_ceo = CEOProfile(cid, name or f"CEO {idx}", domains or ["general","custom"],
                            ["/v1/route","/v1/execute"], 2, 3, 0.05, "flash")
        self._ceos.append(new_ceo)
        budget = TokenBudget(total=int(self._global_budget.total * new_ceo.budget_percent) if self._global_budget else 100000)
        self._ceo_budgets[new_ceo.id] = budget
        self._custom_ceo_count = len(self._ceos)
        self._in_custom_mode = True
        self.profile = f"custom-{len(self._ceos)}"
        return new_ceo

    def remove_ceo(self, ceo_id: str) -> bool:
        for i, c in enumerate(self._ceos):
            if c.id == ceo_id:
                self._ceos.pop(i)
                self._ceo_budgets.pop(ceo_id, None)
                self._custom_ceo_count = len(self._ceos)
                self.profile = f"custom-{len(self._ceos)}"
                self._rebuild_maps()
                return True
        return False

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
class WorkflowStep:
    id: str
    role: str
    system_prompt: str
    model_pref: str = "medium"

WORKFLOW_CHAINS = {
    "code-verify": {
        "name": "Code & Verify",
        "steps": [
            WorkflowStep("ws-code", "coder", "You are an expert programmer. Write complete, working code for the given task."),
            WorkflowStep("ws-think", "thinker", "You are a logical analyst. Analyze the code above for edge cases, bugs, and correctness."),
            WorkflowStep("ws-errors", "error_finder", "You are a strict code reviewer. Find ALL errors, bugs, and issues in the code."),
            WorkflowStep("ws-confirm", "confirmer", "You are a quality assurer. Confirm whether the code passes all checks or needs fixes."),
            WorkflowStep("ws-idea", "idea_gen", "You are a creative problem solver. Suggest improvements and alternative approaches."),
            WorkflowStep("ws-code2", "coder", "You are an expert programmer. Rewrite the code incorporating all fixes and improvements found above."),
            WorkflowStep("ws-errors2", "error_fixer", "You are a strict code reviewer. Verify ALL errors were fixed and fix any remaining ones."),
        ]
    },
    "research-validate": {
        "name": "Research & Validate",
        "steps": [
            WorkflowStep("ws-plan", "planner", "You are a research planner. Create a detailed research plan for the topic."),
            WorkflowStep("ws-explore", "explorer", "You are a deep researcher. Explore the topic thoroughly with multiple perspectives."),
            WorkflowStep("ws-analyze", "analyst", "You are a data analyst. Analyze the findings for patterns, insights, and conclusions."),
            WorkflowStep("ws-verify", "verifier", "You are a fact-checker. Verify all claims and flag any unsupported statements."),
            WorkflowStep("ws-synth", "synthesizer", "You are a research synthesizer. Synthesize everything into a final report."),
        ]
    },
    "creative-iterate": {
        "name": "Creative & Iterate",
        "steps": [
            WorkflowStep("ws-idea-cr", "idea_gen", "You are a creative brainstormer. Generate multiple creative ideas for the given brief."),
            WorkflowStep("ws-dev", "developer", "You are a content developer. Develop the best ideas into full content."),
            WorkflowStep("ws-review-cr", "reviewer", "You are a constructive critic. Review the content and suggest improvements."),
            WorkflowStep("ws-polish", "polisher", "You are a perfectionist. Polish the content to a final, publishable state."),
        ]
    },
}

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
api_configs: list[APIConfig] = [copy.deepcopy(a) for a in DEFAULT_APIS]
