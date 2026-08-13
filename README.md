<div align="center">

![MAIK — Multi-Agent Intelligence Kernel](docs/maik-banner.png)

# MAIK — Multi-Agent Intelligence Kernel

### The world's first AI agent system that thinks, remembers, grades itself, and gets smarter every single run.

**v3.0.0 · Free-First · Self-Learning · Battle-Tested (52/52 tests passing)**

[Get Started ↓](#one-command-install) · [How It Works](#why-maik-changes-everything) · [Architecture](#architecture) · [Benchmarks](#benchmarks--the-flywheel-that-never-stops-learning)

</div>

---

## One-Command Install

No paid API keys required. No credit card. No complex setup. **Run one command for your OS, then just type `maik` — you are ready.**

| OS | One Command (copy & paste) |
|---|---|
| **Windows (PowerShell)** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git; cd maik-demo; pip install -r requirements.txt; python -m maik_kernel.cli init` |
| **Linux** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git && cd maik-demo && pip install -r requirements.txt && python3 -m maik_kernel.cli init` |
| **macOS** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git && cd maik-demo && pip3 install -r requirements.txt && python3 -m maik_kernel.cli init` |

After install, the moment of truth:

```powershell
maik solve "What is 17 times 23 minus 9?"
maik bench        # live benchmark, judged against ground truth
maik flywheel     # watch it learn and rewrite its own routing rules
```

> **Free-first by design.** MAIK routes every call through free providers first and only escalates to paid models when the grade gate demands it — so you can run it today with **zero dollars** in API spending. Your keys are encrypted at rest (Fernet/AES) and never committed to GitHub.

---

## Why MAIK Changes Everything

Every AI agent framework on the market today shares one fatal flaw: **they ask a model a question and believe the answer.** They have no memory of past mistakes, no way to catch a hallucination, no way to learn which expert is actually best at which job, and no accountability for cost. MAIK was built to fix all four — and it does, with mechanisms no other open-source framework ships.

| MAIK's Pros (built, tested, passing) | What Everyone Else Lacks |
|---|---|
| ✅ **52 automated tests — 52 passing.** Every module is verified, not claimed. | ❌ Demos that break the moment you attach a real API key (authentication errors, silent failures) |
| ✅ **Pattern Library — the signature invention.** Specialist patterns with signatures, tier hints, and performance decay. MAIK *knows* which expert to call for which problem. | ❌ Blind round-robin or single-model routing; no specialist registry |
| ✅ **Contradiction mining.** When two tiers give conflicting answers, MAIK detects the conflict, runs a postmortem, and records a permanent reroute rule. Hallucinations literally teach the system. | ❌ Hallucinations go unnoticed forever; users catch them, not the system |
| ✅ **ELO learning engine (K=16).** Experts earn chess-style ratings per domain. Proven experts get the work. | ❌ Every model starts fresh every session; no cumulative expertise |
| ✅ **Self-improving flywheel.** Bench → mine contradictions → update routing → re-bench. Accuracy climbs every revolution — automatically. | ❌ Static systems. Accuracy today = accuracy forever. |
| ✅ **Free-first provider ladder + circuit breakers.** Free gateways first, escalate only when confidence fails. Failed providers are quarantined for 60s — calls never die silently. | ❌ Hardcoded single providers. One outage, everything stops. |
| ✅ **Cost ledger per CEO and per task.** You see exactly where every cent went. Budget tripwires stop runaway spending. | ❌ Cost tracking that lives in your credit card statement |
| ✅ **L1/L2/L3 memory + ThoughtVDB.** Working context, persistent episodes, distilled long-term facts, similarity search. MAIK remembers what worked last week. | ❌ Amnesia by design — nothing persists between runs |
| ✅ **Executive Council governance.** 12 specialist CEOs, individual budgets, friction dial (0–10), stop-light safety gates. | ❌ Flat agent swarms with no hierarchy, no budgets, no safety stops |

**The numbers speak:** 15 core modules, 9 test suites, 26 ground-truth benchmark problems, deterministic offline mode for zero-key testing, and a codebase where every phase (A through G) was completed and verified before moving on.

---

## Architecture

![MAIK Architecture](docs/architecture.png)

MAIK is a **backend-first orchestration kernel**. Nothing in the core imports a web framework — the CLI, web UI, and GUI are thin frontends over a tested engine.

| Layer | Modules | What It Does |
|---|---|---|
| **Gateway** | `cli.py` | `maik solve`, `bench`, `status`, `flywheel`, `init` — one command for everything |
| **Execution** | `executor.py` + `safety.py` | Tiered cascade: solve cheap → grade → escalate. Stop-light gates and budget tripwires on every task |
| **Routing** | `router.py` + `pattern_lib.py` | CEO-aware routing, persistent SQLite pattern cache, the Pattern Library with hot-swap specialist adapters |
| **Providers** | `providers.py` + `stub_provider.py` | Free-first ladder, independent circuit breakers per provider, deterministic stub for offline testing |
| **Memory** | `memory.py` | L1 working context, L2 persistent episodes, L3 distilled facts, ThoughtVDB similarity search |
| **Learning** | `learn.py` + `flywheel.py` | ELO ratings, postmortems, contradiction mining, automatic reroute-rule generation, self re-benchmarking |
| **Benchmark** | `bench_truth.py` | 26 ground-truth problems with automated correctness judging — MAIK grades itself honestly |
| **Governance** | `config.py` + `blackboard.py` | 12-CEO Executive Council, per-CEO budgets, friction dial, thread-safe shared memory |
| **Secrets** | `secrets.py` | Fernet-encrypted `.env` at rest; keys never appear in the repo, ever |

---

## Benchmarks & the Flywheel That Never Stops Learning

MAIK doesn't just run — it **measures**. `maik bench` executes the problem suite and judges every answer against hand-written ground truth, then feeds the results into the learning engine. `maik flywheel` closes the loop:

1. **Bench** the system and collect every wrong answer.
2. **Mine contradictions** between tiers — every conflict becomes evidence.
3. **Update ELO ratings** and generate permanent `reroute_rules.json`.
4. **Re-bench** — accuracy delta proves whether the system improved.

This is the difference between a chatbot wrapper and an intelligence kernel: **the system that ships with MAIK gets more accurate the more you use it**, with no human tuning required.

---

## Philosophy & Credits

> *"I asked AI for help building my ideas, not the architecture or code, just ideas, and it told me they were impossible — that they already existed. So I built a proof. This is it."*

MAIK was designed and authored by **Rehan Muhammad** — an independent developer and the creator of the independently-verified Z++ subset-sum solver. Every claim in this README is backed by tests you can run yourself. Don't take the word of an AI; take the word of `pytest`.

**License:** MIT · **Contributions:** open to serious collaborators
**Issues & ideas:** open an issue on GitHub — design authority stays with the author.

<div align="center">

**Built by Rehan Muhammad — an independent developer.**

</div>
