# MAIK — Multi-Agent Intelligence Kernel

**119/119 tests · 12/2 CEOs · 21 sections · 150+ features**

MAIK is a production-grade multi-agent orchestration framework built on an **Executive Council** architecture — N CEOs each owning specific domains and API endpoints, with per-CEO budgets, hierarchies, and model preferences.

## Quick Start

```bash
pip install -r requirements.txt
python test_full.py          # 119 tests, all pass (offline)
python -m uvicorn main:app   # Start server on port 8000
```

## Multi-CEO Architecture

### Full Profile (12 CEOs)

Each CEO owns a slice of the API surface. Every request is routed to the right CEO by domain + API prefix. Each CEO has dedicated budget, managers, and model preference.

| CEO | Domain | APIs | Managers | Budget |
|-----|--------|------|----------|--------|
| Code & Engineering | code, programming, api, backend | `/v1/route`, `/v1/execute`, `/v1/expert/*` | 4 | 15% |
| Data & Learning | data, ml, ai, training | `/v1/learn`, `/v1/evolution/*` | 3 | 12% |
| Knowledge & Memory | knowledge, memory, recall | `/v1/memory/*` | 3 | 10% |
| Safety & Compliance | safety, security, audit, purity | `/v1/safety/*`, `/v1/purity/*` | 3 | 10% |
| Cognition & Research | cognition, logic, reasoning | `/v1/cognitive/*`, `/v1/boolean/*` | 3 | 10% |
| Corporate & Meta | corporate, meta, governance | `/v1/library/*`, `/v1/meta/*` | 3 | 8% |
| Operations | ops, schedule, monitor, health | `/v1/schedule/*`, `/v1/stats`, `/v1/info` | 2 | 7% |
| Creative & Design | creative, design, writing | route/execute creative tasks | 3 | 8% |
| Security & Audit | security, audit, vulnerability | route/execute security tasks | 3 | 7% |
| Deep Research | research, explore, analyze | cognitive research endpoints | 3 | 6% |
| Infrastructure | infra, deploy, devops | schedule, expert bridge | 2 | 4% |
| Product Management | product, strategy, roadmap | route/execute planning tasks | 2 | 3% |

### Light Profile (2 CEOs)

For constrained budgets — same full feature set, 2 CEOs, fewer managers.

| CEO | Domain | APIs | Managers | Budget |
|-----|--------|------|----------|--------|
| Core Intelligence | code, planning, math, logic, learning, stats | `/v1/route`, `/v1/execute`, `/v1/learn`, `/v1/stats`, `/v1/info`, `/v1/boolean/*` | 2 | 60% |
| Support & Safety | safety, memory, schedule, purity, cognitive, library | `/v1/safety/*`, `/v1/memory/*`, `/v1/schedule/*`, `/v1/purity/*`, `/v1/cognitive/*`, `/v1/library/*`, `/v1/meta/*` | 2 | 40% |

### Profile Switching

```bash
# Check current council
GET /v1/council

# Switch to light profile (2 CEOs)
POST /v1/council/switch?profile=light

# Switch back to full (12 CEOs)
POST /v1/council/switch?profile=full
```

## All 21 Sections

| Section | Feature | Module | Endpoints |
|---------|---------|--------|-----------|
| 1 | Token Budget | `config.py` | — |
| 2 | Corporate Hierarchy | `config.py` | — |
| 3 | Expert Manifest | `config.py` | — |
| 4 | Blackboard + Notes | `blackboard.py` | — |
| 5 | Safety | `safety_engine.py` | `/v1/safety/*` |
| 6 | Thought VDB | `memory_engine.py` | `/v1/memory/thought` |
| 7 | Model Chain | `config.py` | — |
| 8 | L1/L2/L3 Memory | `memory_engine.py` | `/v1/memory/*` |
| 9 | Scheduler | `scheduler_engine.py` | `/v1/schedule/*` |
| 10 | PBT Evolution | `evolution_engine.py` | `/v1/evolution/*` |
| 11 | Meta Controller | `meta_controller.py` | `/v1/meta/*` |
| 12 | Expert Bridge | `expert_bridge.py` | `/v1/expert/*` |
| 13 | Cognitive | `cognitive_engine.py` | `/v1/cognitive/*` |
| 14 | Corporate Library | `corporate_engine.py` | `/v1/library/*` |
| 15 | Purity Filter | `purity_filter.py` | `/v1/purity/*` |
| 16 | Co-creation | `tree_engine.py` | `/v1/execute` |
| 17 | Socratic | `tree_engine.py` | `/v1/execute` |
| 18 | Boolean Algebra | `boolean_engine.py` | `/v1/boolean/*` |
| 19 | Predictive Pruning | `tree_engine.py` | — |
| 20 | Pattern Cache | `router_engine.py` | `/v1/cache/clear` |
| 21 | Recursive Decomposition | `tree_engine.py` | `/v1/execute` |

## Model Chain

| Tier | Model | Cost | Roles |
|------|-------|------|-------|
| flash | Gemini 2.0 Flash | $0.0001 | route, explore, classify, creative |
| small | Qwen 2.5 Coder 3B | $0.0003 | decompose, review_simple, fact_check |
| medium | Claude 3 Haiku | $0.0008 | execute, review, plan |
| large | GPT-4o Mini | $0.0015 | synthesize, verify, security |

## Project Structure

```
maik-demo/
  main.py              # FastAPI server — 20+ endpoints, CEO-aware routing
  config.py            # ExecutiveCouncil, CEOProfile, CEO_FULL/CEO_LIGHT, TokenBudget
  blackboard.py        # Blackboard + Internal Notes + ThoughtVDB integration
  router_engine.py     # CEO-aware Model Router with Pattern Cache
  tree_engine.py       # CEO-specific Agent Tree + Corporate Hierarchy
  learn_engine.py      # Self-Improvement Flywheel (ELO + postmortems)
  safety_engine.py     # Circuit Breakers, Triads, Stop Light
  memory_engine.py     # L1/L2/L3 Memory, Thought VDB
  scheduler_engine.py  # Cost-Aware Priority Scheduler
  cognitive_engine.py  # Incubation, Abduction, Analogy, Wandering
  corporate_engine.py  # Library Registry, Permission System
  purity_filter.py     # Secret/Toxin/Malicious Detection
  meta_controller.py   # Meta-Agent, State Machine
  evolution_engine.py  # PBT, Reward Shaping
  boolean_engine.py    # Agent Gates, Circuits, Neural Voting
  expert_bridge.py     # Subprocess Expert Bridge
  test_full.py         # 119 tests — all 21 sections + multi-CEO
  requirements.txt     # fastapi, uvicorn, pydantic
```

## License

MIT
