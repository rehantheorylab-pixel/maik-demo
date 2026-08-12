# MAIK Kernel — Upgraded Architecture (v3)

**Author: Rehan Muhammad (design authority) + Manus AI (architecture upgrade) | August 12, 2026**

This architecture upgrades the maik-demo (v2) design where the audit showed weakness, keeps what the audit showed was strong, and adds the signature invention. Every upgrade is marked so the design authority can see exactly what changed.

## 1. What was kept from maik-demo v2 (audit-verified as working)

The 12-CEO Executive Council with per-CEO token budgets, the friction dial, the model-tier vocabulary (flash/small/medium/large), the blackboard with internal notes, the safety stop-light, and the L1/L2/L3 memory structure all passed the audit: they instantiate, route, and track correctly. They form the governance skeleton of v3.

## 2. Upgrades over v2 (marked: [U])

| # | Area | v2 (maik-demo) | v3 (this architecture) |
|---|---|---|---|
| U1 | Execution | litellm → OpenRouter with broken auth; LLM calls die silently | **Provider ladder**: ordered list of providers (OpenRouter free → apifreellm → mastra gateway → agnes-ai → user keys), automatic failover on 401/429/timeout, circuit-breaker per provider |
| U2 | Testing | 119 offline structure tests passing despite LLM_ERROR solutions | **Two-layer tests**: offline unit tests (structure) + `bench_truth` ground-truth suite (correctness). A run only "passes" when the answer matches the known answer |
| U3 | Cost honesty | Token budgets tracked but never priced | **Cost ledger**: real $/M-token pricing per model, cost per task logged, per-CEO cost attribution — this is what makes the consumer-GPU thesis measurable |
| U4 | Key hygiene | .env.example only; keys risk committed | Encrypted `.env` (cryptography Fernet), `secrets.py` decrypts on demand, `.gitignore` hard-blocks keys |
| U5 | Routing cache | In-memory pattern cache, lost on restart | **Persistent pattern DB** (SQLite + LMDB optional): routing decisions become the training corpus for the pattern library — cache is the *seed* of the invention |
| U6 | Learning loop | ELO + postmortem structures, never fed real data | **Flywheel wired end-to-end**: benchmark run → contradictions mined → reroute rules updated → re-run, closed loop on real tasks |

## 3. Module map (the build order = dependency order)

```
maik_kernel/
├── config.py          — ExecutiveCouncil, CEOs, budgets, friction dial, model tiers [keep]
├── secrets.py         — encrypted .env load (U4)
├── providers.py       — provider ladder + failover + per-provider circuit breaker (U1)
├── blackboard.py      — shared memory + internal notes [keep]
├── router.py          — CEO-aware routing + persistent pattern cache (U5)
├── executor.py        — agent tree execution with tiered cascade (U1+U3)
├── safety.py          — stop-light, triads, budget tripwires [keep]
├── memory.py          — L1/L2/L3 + thought VDB [keep]
├── learn.py           — ELO, postmortems, contradiction mining (U6)
├── pattern_lib.py     — Pattern Library v0: specialist registry, routing table, hot-swap (invention)
├── bench_truth.py     — ground-truth benchmark suite (U2)
├── flywheel.py        — benchmark → mine → improve → re-run loop (U6)
└── cli.py             — single command: `maik solve <problem>` + `maik bench`
```

## 4. The Tiered Cascade (execution core, upgraded)

Every problem flows: **free flash model first** (routing + classification, ~free) → if confidence ≥ threshold, execute on flash/small; if low confidence or execution fails, escalate one tier; max 2 escalations (U-cost ceiling). The provider ladder (U1) makes this work without a single paid key. Escalation is the only cost sink, and the cost ledger (U3) proves how rarely it's needed — that number IS the paper.

## 5. The Pattern Library v0 (the invention, minimal viable form)

Full activation-motif distillation is not yet buildable on the sandbox (needs GPU training runs), so v0 is the **architecture-complete, data-complete** version: the routing cache's accumulated decisions form a versioned pattern DB (problem-type → best CEO/expert/model/notes, with decay and performance curves). Specialists are registry entries that can later be swapped for real LoRA adapters without changing interfaces. When real distillation is available, each registry entry gains a `weights` slot. The public API of v0 and v1 are identical by design — that is the load-bearing decision.

## 6. Success criteria (no phase advances without these)

Phase A: council instantiates, friction dial changes behavior, blackboard round-trips. Phase B: real answer from a real free endpoint, failover proven by killing one provider, cascade proven by low-confidence problem. Phase C: ELO moves on win/loss, postmortem recorded. Phase D: pattern DB persists across restarts, hot-swap changes routing live. Phase E: bench_truth ≥ 50 problems, accuracy/cost logged per problem. Phase F: flywheel changes at least one routing rule after mining. Phase G: `maik solve` one-liner, release zip.
