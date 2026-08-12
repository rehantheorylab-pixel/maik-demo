from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from config import TokenBudget, cfg, corp, experts, safety_cfg, memory_cfg, cognitive_cfg, evolution_cfg, council, ExecutiveCouncil
from blackboard import blackboard, internal_notes
from router_engine import route, clear_cache, cache_stats, ceo_routing_log
from tree_engine import execute, get_execution_log, ceo_execution_breakdown
from learn_engine import learn, get_stats
from safety_engine import stop_light, kill_switch, _safety_triad, monotonic, anti_pattern, CircuitBreaker
from memory_engine import l1_memory, l2_memory, l3_memory, thought_vdb
from scheduler_engine import scheduler
from cognitive_engine import incubation, abductor, analogizer, wanderer, chunker
from corporate_engine import corp_library, perm_system
from purity_filter import purity
from meta_controller import meta_agent, state_machine
from evolution_engine import pbt, reward_shaper
from boolean_engine import voter, AgentGate, GateOp, AgentCircuit
from expert_bridge import expert_bridge

app = FastAPI(title="MAIK - Multi-Agent Intelligence Kernel", version="2.0.0",
              description="Multi-CEO architecture: 12 CEOs (full) or 2 CEOs (light), each owning specific API domains")

class RouteRequest(BaseModel):
    problem: str = Field(..., min_length=1, max_length=5000)
    domain: str = Field("", max_length=200)
    budget_total: int = Field(100_000, ge=1000, le=10_000_000)

class RouteResponse(BaseModel):
    expert: str; model: str; model_full: str; problem_type: str
    confidence: float; domain: str; explanation: str; cached: bool
    ceo: str; ceo_name: str; ceo_budget: str
    budget: str; budget_mode: str; cache_stats: dict

class ExecuteRequest(BaseModel):
    problem: str = Field(..., min_length=1, max_length=10000)
    domain: str = Field(""); budget_total: int = Field(100_000, ge=1000, le=10_000_000)
    depth: int = Field(0, ge=0, le=5); parent_id: str = Field("")

class ExecuteResponse(BaseModel):
    solution: str; confidence: float; depth: int; ceo: str
    agents_used: list; budget: str; budget_mode: str; ceo_execution_counts: dict
    notes: Optional[dict] = None; chat_log: Optional[list] = None
    agents_log: Optional[list] = None; sub_problems: Optional[list] = None

class LearnRequest(BaseModel):
    problem: str = Field(..., min_length=1, max_length=10000)
    solution: str = Field(""); outcome: str = Field("success", pattern="^(success|failure|partial)$")
    agents_used: list = Field(default_factory=list)
    confidence: float = Field(0.75, ge=0, le=1)
    tokens: int = Field(0, ge=0); duration_ms: int = Field(0, ge=0)

class LearnResponse(BaseModel):
    learned: bool; run_id: str; elo_updated: dict; postmortem: dict
    contradictions: list; replay_queue_size: int; total_runs: int
    total_postmortems: int; pattern: dict; budget_advice: str

class InfoResponse(BaseModel):
    system: str; version: str; profile: str; num_ceos: int
    friction_dial: int; hierarchy: list; experts: list; models: list
    cache_hit_rate: float; budget_warning_pct: float; budget_critical_pct: float
    stop_light: str; scheduler_queue: int; violations: int

class StatsResponse(BaseModel):
    total_runs: int; total_postmortems: int; elo_ratings: dict
    replay_queue: int; contradictions: int; success_rate: float
    avg_confidence: float; avg_tokens: float; ceo_breakdown: dict

class ThoughtRequest(BaseModel):
    agent_id: str; thought: str; tags: list = Field(default_factory=list); confidence: float = 0.5

class MemoryRequest(BaseModel):
    key: str; value: str; confidence: float = 0.7

class ScheduleRequest(BaseModel):
    description: str; agent_type: str = "general"; estimated_cost: float = 100.0; urgency: float = 0.5

class IdeaRequest(BaseModel):
    agent_id: str; idea: str; source: str = ""; tags: list = Field(default_factory=list)

class LibraryRequest(BaseModel):
    agent_id: str; name: str; content: str; domain: str = ""; version: str = "0.1.0"; visibility: str = "internal"

@app.get("/")
def root():
    return {"system": "MAIK", "version": "2.0.0", "profile": council.profile, "num_ceos": council.num_ceos,
            "ceos": [{"id": c.id, "name": c.name, "managers": c.min_managers, "api_count": len(c.api_prefixes)} for c in council.ceo_list]}

@app.post("/v1/route", response_model=RouteResponse)
def api_route(req: RouteRequest):
    budget = TokenBudget(total=req.budget_total)
    result = route(req.problem, req.domain, budget)
    return RouteResponse(**result)

@app.post("/v1/execute", response_model=ExecuteResponse)
def api_execute(req: ExecuteRequest):
    budget = TokenBudget(total=req.budget_total)
    result = execute(req.problem, req.domain, budget, req.depth, req.parent_id)
    return ExecuteResponse(**result)

@app.post("/v1/learn", response_model=LearnResponse)
def api_learn(req: LearnRequest):
    result = learn(req.problem, req.solution, req.outcome, req.agents_used, req.confidence, req.tokens, req.duration_ms)
    return LearnResponse(**result)

@app.get("/v1/stats", response_model=StatsResponse)
def api_stats():
    return StatsResponse(ceo_breakdown=ceo_execution_breakdown(), **get_stats())

@app.get("/v1/info", response_model=InfoResponse)
def api_info():
    return InfoResponse(
        system="MAIK", version="2.0.0", profile=council.profile, num_ceos=council.num_ceos,
        friction_dial=cfg.friction_dial,
        hierarchy=[corp.role_at_depth(d) for d in range(5)],
        experts=list(experts.experts.keys()),
        models=[m["name"] for m in cfg.model_chain],
        cache_hit_rate=cache_stats()["hit_rate"],
        budget_warning_pct=TokenBudget().warning_pct,
        budget_critical_pct=TokenBudget().critical_pct,
        stop_light=stop_light.status(),
        scheduler_queue=scheduler.stats()["queue_size"],
        violations=purity.violation_count(),
    )

@app.get("/v1/council")
def api_council():
    return {"profile": council.profile, "ceos": council.list_ceos(), "total_ceos": council.num_ceos}

@app.post("/v1/council/switch")
def api_council_switch(profile: str = "full"):
    if profile not in ("full", "light"):
        raise HTTPException(400, "Profile must be 'full' (12 CEOs) or 'light' (2 CEOs)")
    council.configure(profile)
    return {"profile": profile, "ceos": council.list_ceos(), "message": f"Switched to {profile} profile with {council.num_ceos} CEOs"}

@app.post("/v1/cache/clear")
def api_clear_cache():
    clear_cache()
    return {"status": "cleared", "cache_stats": cache_stats()}

@app.get("/v1/safety/status")
def safety_status():
    return {"stop_light": stop_light.status(), "kill_switch": kill_switch.check(),
            "violations": purity.violation_count(), "scheduler_queue": scheduler.stats()["queue_size"]}

@app.post("/v1/safety/pause")
def safety_pause():
    stop_light.set_red(); return {"status": "paused", "stop_light": "red"}

@app.post("/v1/safety/resume")
def safety_resume():
    stop_light.set_green(); return {"status": "resumed", "stop_light": "green"}

@app.get("/v1/memory/recall")
def memory_recall(query: str = "", top_k: int = 5):
    return {"l1": l1_memory.recall(query, top_k), "l2": l2_memory.recall(query, top_k),
            "l3": l3_memory.recall(query, top_k), "thoughts": thought_vdb.query(query, top_k)}

@app.post("/v1/memory/store")
def memory_store(req: MemoryRequest):
    l1_memory.store(req.key, req.value, {"confidence": req.confidence}); return {"stored": True}

@app.post("/v1/memory/thought")
def memory_thought(req: ThoughtRequest):
    thought_vdb.inject(req.agent_id, req.thought, req.tags, req.confidence); return {"injected": True}

@app.post("/v1/schedule/enqueue")
def schedule_enqueue(req: ScheduleRequest):
    task_id = scheduler.enqueue(req.description, req.agent_type, req.estimated_cost, req.urgency)
    return {"task_id": task_id, "queue_size": scheduler.stats()["queue_size"]}

@app.get("/v1/schedule/status")
def schedule_status(): return scheduler.stats()

@app.get("/v1/schedule/next")
def schedule_next(): return {"next_up": scheduler.next_up(5)}

@app.post("/v1/cognitive/seed")
def cognitive_seed(req: IdeaRequest):
    incubation.seed(req.agent_id, req.idea, req.source, req.tags)
    return {"seeded": True, "total_ideas": len(incubation.hot_ideas())}

@app.post("/v1/cognitive/percolate")
def cognitive_percolate():
    hatched = incubation.percolate()
    return {"hatched": hatched, "hot_ideas": len(incubation.hot_ideas())}

@app.post("/v1/cognitive/hatch")
def cognitive_hatch():
    idea = incubation.hatch_one(); return {"hatched": idea is not None, "idea": idea}

@app.get("/v1/cognitive/abduce")
def cognitive_abduce(observation: str = ""):
    return {"explanations": abductor.best_explanation(observation)}

@app.get("/v1/cognitive/analogize")
def cognitive_analogize(problem: str = ""):
    return {"analogies": analogizer.find_analogies(problem)}

@app.post("/v1/library/contribute")
def library_contribute(req: LibraryRequest):
    lib_id = corp_library.contribute(req.agent_id, req.name, req.content, req.domain, req.version, req.visibility)
    if lib_id is None:
        raise HTTPException(403, "Insufficient permissions")
    return {"lib_id": lib_id}

@app.get("/v1/library/search")
def library_search(query: str = "", domain: str = ""):
    return {"results": corp_library.search(query, domain)}

@app.get("/v1/library/stats")
def library_stats(): return corp_library.stats()

@app.post("/v1/purity/check")
def purity_check(text: str = ""): return purity.check(text)

@app.post("/v1/purity/filter")
def purity_filter(text: str = ""): return {"filtered": purity.filter_text(text)}

@app.get("/v1/meta/status")
def meta_status(): return meta_agent.stats()

@app.post("/v1/meta/delegate")
def meta_delegate(sub_agent: str = "", task: str = ""):
    return {"decision_id": meta_agent.delegate(sub_agent, task)}

@app.get("/v1/evolution/status")
def evolution_status(): return pbt.stats()

@app.post("/v1/evolution/evolve")
def evolution_evolve():
    gen = pbt.evolve(); return {"generation": gen, "best_fitness": pbt.stats()["best_fitness"]}

@app.get("/v1/boolean/vote")
def boolean_vote(votes_json: str = "{}"):
    import json as _json; return voter.vote(_json.loads(votes_json))

@app.post("/v1/expert/call")
def expert_call(name: str = "", input_json: str = "{}"):
    import json as _json; return expert_bridge.call_expert(name, _json.loads(input_json))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
