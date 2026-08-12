# MAIK Kernel

**Multi-Agent Intelligence Kernel — v3.0.0 | Author: Rehan Muhammad | August 2026**

MAIK is a backend-first multi-agent orchestration kernel. It assigns an Executive Council of specialist CEOs to every problem, routes work through a tiered model cascade (free first, escalate only when confidence demands it), tracks costs and budgets per CEO, learns from every run through a persistent pattern cache, and benchmarks itself against ground truth. The frontend (CLI, web, GUI) wraps this package; nothing in the core imports a web framework.

## Architecture

```mermaid
flowchart TD
    CLI["maik solve / maik bench"] --> EXEC[executor.py]
    EXEC --> ROUTE[router.py]
    ROUTE --> PCACHE[("Pattern Cache (SQLite)")]
    PCACHE -.seed.-. PLIB[pattern_lib.py — Phase D]
    EXEC --> PROV[providers.py — provider ladder]
    PROV --> F1[Free: local gateway / OpenRouter free]
    PROV --> F2[Escalation: OpenAI / Anthropic / Gemini]
    PROV --> STUB[stub (offline testing)]
    F1 --> EXEC
    F2 --> EXEC
    EXEC --> SAFETY[safety.py — stop-light & tripwires]
    EXEC --> BB[blackboard.py — shared memory]
    EXEC --> MEM[memory.py — L1/L2/L3 — Phase C]
    EXEC --> LRN[learn.py — ELO, postmortems — Phase C]
    EXEC --> COST[cost ledger — $/task, $/CEO]
    EXEC --> BENCH[bench_truth.py — ground truth — Phase E]
    BENCH --> FLYWHEEL[flywheel.py — mine contradictions → reroute — Phase F]
    FLYWHEEL --> ROUTE
```

## Quick start

```bash
pip install -r requirements.txt
MAIK_STUB=1 python3 smoke.py          # offline smoke test (deterministic stub)
python3 smoke.py                      # live: free gateways first, no paid key required


## Secrets

`.env` is encrypted at rest (Fernet/AES-128-CBC). The decryption key comes from the `MAIK_KEY` env var or a machine-local derivation. **Never commit `.env`** — `.gitignore` blocks it; only `.env.example` (placeholders) ships with the repo. Leave all values empty to run on free providers only.

## Provider ladder (why calls never die silently)

Calls try providers in order: local gateway → OpenRouter free models → your paid keys (OpenAI/Anthropic/Gemini, optional). Each provider has an independent circuit breaker (3 failures → open for 60 s), and the cascade escalates model tier only when the grade gate fails — the cost ledger proves escalation is rare. `MAIK_STUB=1` prepends a deterministic local stand-in for offline testing and zero-key demos.

## Phases

| Phase | Status | Contents |
|---|---|---|
| A — Foundation | DONE | config (12 CEOs, budgets, friction dial), blackboard, router + persistent pattern cache, secrets |
| B — Intelligence | DONE (core) | provider ladder, tiered cascade executor, safety gate, cost ledger |
| C — Memory & Learning | DONE | L1/L2/L3 memory, ELO, postmortems, contradiction mining |
| D — Pattern Library | DONE | specialist registry, hot-swap, the signature invention |
| E — Benchmark | DONE | 24 ground-truth problems, correctness judging, accuracy + cost table |
| F — Flywheel | DONE | bench → mine contradictions → reroute rules → re-bench |
| G — CLI | DONE | `maik solve/bench/status/flywheel/init` |

## CLI

```bash
python3 -m maik_kernel.cli init                     # first run: creates encrypted .env
python3 -m maik_kernel.cli solve "Calculate 17 x 23"
python3 -m maik_kernel.cli bench                    # live benchmark, judged vs ground truth
python3 -m maik_kernel.cli bench --stub             # offline stub mode (zero API keys)
python3 -m maik_kernel.cli bench --n 10             # first 10 problems only
python3 -m maik_kernel.cli status                   # learning / memory / pattern health
python3 -m maik_kernel.cli flywheel                 # run the closed learning loop
python3 -m maik_kernel.cli flywheel --revolutions 3 # three loop revolutions
```

## Verification

```bash
MAIK_STUB=1 python3 smoke.py          # offline smoke test (deterministic stub)
python3 -m pytest tests               # 52 unit tests — all passing
python3 -m maik_kernel.cli bench      # live: free gateways first, no paid key required
```
