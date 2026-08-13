<div align="center">

![MAIK — Multi-Agent Intelligence Kernel](docs/maik-banner.png)

# MAIK — Multi-Agent Intelligence Kernel

### The world's first AI agent system that thinks, remembers, grades itself, and gets smarter every single run.

**v3.2.0 · Free-First · Self-Learning · Org-Aware · CEO-as-Operator · Battle-Tested (146/146 tests passing)**

[Get Started ↓](#one-command-install) · [The Company](#v310----the-org-layer-agents-with-a-real-company) · [The CEO as Operator](#v320----the-live-layer-real-models-a-prompt-department-an-api-department-and-a-ceo-console) · [How It Works](#why-maik-changes-everything) · [Architecture](#architecture) · [Benchmarks](#benchmarks--the-flywheel-that-never-stops-learning)

</div>

---

## One-Command Install

No paid API keys required. No credit card. No complex setup. **Run one command for your OS, then just type `maik` — you are ready.**

| OS | One Command (copy & paste) |
|---|---|
| **Windows (PowerShell)** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git; cd maik-demo; pip install -r requirements.txt; python -m maik_kernel.cli init` |
| **Linux** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git && cd maik-demo && pip install -r requirements.txt && python3 -m maik_kernel.cli init` |
| **macOS** | `git clone https://github.com/rehantheorylab-pixel/maik-demo.git && cd maik-demo && pip3 install -r requirements.txt && python3 -m maik_kernel.cli init` |

> **Shortcut on Windows:** `Set-Alias maik 'python -m maik_kernel.cli'` — then every command below becomes just `maik ...` (add it to your PowerShell profile to keep it forever).

After install, the moment of truth:

```powershell
maik solve "What is 17 times 23 minus 9?"
maik bench        # live benchmark, judged against ground truth
maik flywheel     # watch it learn and rewrite its own routing rules
```

> **Free-first by design.** MAIK routes every call through free providers first and only escalates to paid models when the grade gate demands it — so you can run it today with **zero dollars** in API spending. Your keys are encrypted and fully safe.

## v3.1.0 — The Org Layer: Agents with a Real Company

MAIK v3.1.0 adds a **real company** on top of the intelligence engine. Your agents now have an org chart, IDs, managers, notebooks, chat threads, scoped permissions, and their own system prompts. The CEO acts like a real CEO: it gives commands to managers, managers manage agents, and every agent works within its system prompt — knowing who it is, who its manager is, and exactly what it may touch.

**Every agent is self-aware.** Each node's resolved prompt contains a SELF block with its identity, role, level, manager chain, CEO, sibling agents, capabilities, and the current UTC time — time-aware, never token-obsessed. And because prompts are generated dynamically at runtime, **every feature ships with its prompt rules**: threads, notebooks, MCP tools, and everything added later is automatically documented inside each agent's prompt.

**The chain of prompt authorship** mirrors a real company: you write the CEO prompt, the CEO writes manager prompts, managers write agent prompts, agents write subagent prompts — each guided by built-in prompt quality guidelines (`maik org prompt guide`).

```powershell
maik org status                           # see the whole company: hierarchy, chains, model bindings
maik org add manager <ceo-uid> "Rehan-Ops" engineering
maik org add agent <ceo-uid> "CodeWriter" code_writer --allow-commands --allow-files
maik org bind <node-uid> anthropic/claude-haiku   # pin a specific model to a node
maik org prompt guide --role code_writer          # what a great agent prompt contains
maik org prompt view --node "Chief Code"          # the exact prompt Chief Code sees
maik org notebook write CodeWriter public --text "deployed via CLI"
maik org deploy probe aider                       # probe any external coding CLI (VS Code, Cursor, aider, codex...)
maik org thread create --topic "API choice" --owner <uid>
maik org thread veto --thread-id <id> --owner <uid> --reason "cost too high for this task"
```

## v3.2.0 — The Live Layer: Real Models, a Prompt Department, an API Department, and a CEO Console

v3.1.0 gave MAIK a company. v3.2.0 makes that company **operate in the real world** — with live models, dedicated management departments, and a CEO console that puts the operator in direct control of the machine.

**Real execution with an anti-hallucination verifier (`live_execution.py`).** When keys are configured, MAIK stops being a stub and starts making real LLM calls through the same free-first ladder — with independent verifiers. After an answer is accepted, a *different* model grades it on its own; a `SUSPECT` verdict forces escalation instead of silently shipping a hallucination. Two models against each other, exactly as the original thesis described.

**The Prompt Management Agent (`prompt_management.py`) — the CEO's prompt department.** Prompt quality is the single biggest driver of agent quality, so MAIK now has a dedicated agent whose entire job is prompts: it *writes* prompts from role + mission (with the quality checklist baked in), *grades* every prompt against 8 weighted criteria (identity, role clarity, mission, constraints, output format, error handling, coordination, tone), *auto-upgrades* weak prompts by injecting the missing elements until they pass the bar, and keeps a full *history* of every edit — so no prompt is ever lost.

**The API/Model Management Agent (`api_management.py`) — the finance department.** Every node gets a token budget AND a dollar budget with an 80% tripwire. The department enforces per-provider rate limits with burst control, and when a provider saturates or its circuit opens, it emits the reroute advice so stressed nodes move to healthy providers — before money burns, not after. `maik status` shows a live dashboard of per-node spend and remaining quotas.

**The CEO Access Layer (`ceo_access.py`) — the CEO as operator.** The CEO is no longer just a name in the org chart. It is a console: run PowerShell (Windows) or shell commands, create files with path-escape protection, probe and spawn external coding CLIs (aider, opencode, codex, claude-code, gemini-cli, VS Code, Cursor...), connect to any MCP server and call its tools — every action dry-run first, every action written to an immutable audit trail, and every action gated by the org chart's power system so permissions can never be quietly exceeded.

```powershell
maik solve "find prime factors of 9999991"   # now runs live when keys are present
maik status                                  # org health + API spend dashboard
```

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
| ✅ **Real org chart (v3.1.0).** Managers manage agents, agents delegate to subagents, CEO oversight up the chain of command. Every node knows who it is, who its manager is, who the CEO is. | ❌ Agents that don't know where they sit or who reports to whom |
| ✅ **System prompt engine with 16 role templates.** code_writer, code_tester, code_reviewer, code_debugger, idea_verifier, idea_generator, research_explorer, synthesizer, verifier, and more — merged with CEO default, per-node edits, and a SELF-awareness block (identity, role, manager, siblings, capabilities, UTC time). | ❌ Generic one-size-fits-all prompts; agents that don't know their own role |
| ✅ **WhatsApp-style team threads with real governance.** Post, reply, hold, debate, vote, consensus — and CEO/manager veto that **requires a written reason**, with exactly one counter-argument allowed before the debate re-opens. | ❌ Chat rooms where anyone can close anything; veto without accountability |
| ✅ **Dual public/hidden notebooks per agent.** The public notebook is the team WhatsApp; the hidden one is private to the agent — readable only by its manager chain (CEO oversight). Persisted as JSONL. | ❌ Shared context that is either fully public or fully invisible |
| ✅ **Scoped permissions.** Agents know exactly what they may touch: one file, a project folder, or the full computer. Shell/file/screen/browser powers granted per node; every command runs dry-run-first. | ❌ Unrestricted shell access or none at all |
| ✅ **Model binding per node.** Pin any provider/model to any node — cheap models for subagents, flagship models for the CEO. Free-tier default, paid escalation per node. | ❌ One hardcoded model for every agent |
| ✅ **External CLI + MCP integration.** Spawn aider, opencode, codex, claude-code, gemini-cli and every MCP server (filesystem, browser, shell) as tool plugins. | ❌ Frameworks locked inside their own sandbox |
| ✅ **Live execution + independent verifier (v3.2.0).** Real answers from real models, then a *second, different* model grades them — a SUSPECT verdict forces escalation. Two models against each other: hallucinations caught by the system, not the user. | ❌ "Answer + believe it" architectures with no verification loop |
| ✅ **Prompt Management Agent (v3.2.0).** A dedicated agent that writes, grades, and auto-upgrades prompts for every other agent — 8 weighted quality criteria, version history, never-lose-an-edit. Best prompt = best agent = best CLI in the world. | ❌ Prompts hand-written once and never measured or improved |
| ✅ **API Management Agent (v3.2.0).** Per-node token AND dollar budgets with 80% tripwire, client-side rate limits with burst control, automatic fallback switching, live spend dashboard — the department that watches the money before you spend it. | ❌ Cost awareness that arrives with your credit card bill |
| ✅ **CEO Access Layer (v3.2.0).** The CEO is the operator: PowerShell commands, file creation with path-escape protection, external CLI deployment, MCP tool calls — dry-run first, every action audited, every action power-gated by the org chart. | ❌ Agents with either no real access or unlimited, ungated access |

**The numbers speak:** 19 core modules, 13 test suites, 26 ground-truth benchmark problems, deterministic offline mode for zero-key testing, and a codebase where every phase (A through L) was completed and verified before moving on.

---

## Architecture

![MAIK Architecture](docs/architecture.png)

MAIK is a **backend-first orchestration kernel**. Nothing in the core imports a web framework — the CLI, web UI, and GUI are thin frontends over a tested engine.

| Layer | Modules | What It Does |
|---|---|---|
| **Gateway** | `cli.py` | `maik solve`, `bench`, `status`, `flywheel`, `init` — plus the full `maik org` family (status/add/bind/prompt/notebook/deploy/thread) |
| **Execution** | `executor.py` + `safety.py` | Tiered cascade: solve cheap → grade → escalate. Stop-light gates and budget tripwires on every task |
| **Routing** | `router.py` + `pattern_lib.py` | CEO-aware routing, persistent SQLite pattern cache, the Pattern Library with hot-swap specialist adapters |
| **Providers** | `providers.py` + `stub_provider.py` | Free-first ladder, independent circuit breakers per provider, deterministic stub for offline testing |
| **Memory** | `memory.py` | L1 working context, L2 persistent episodes, L3 distilled facts, ThoughtVDB similarity search |
| **Learning** | `learn.py` + `flywheel.py` | ELO ratings, postmortems, contradiction mining, automatic reroute-rule generation, self re-benchmarking |
| **Benchmark** | `bench_truth.py` | 26 ground-truth problems with automated correctness judging — MAIK grades itself honestly |
| **Governance** | `config.py` + `blackboard.py` | 12-CEO Executive Council, per-CEO budgets, friction dial, thread-safe shared memory |
| **Org (v3.1.0)** | `org_chart.py` + `model_binding.py` | Hierarchy engine (CEO→manager→agent→subagent), persistent bindings, `from_spec` free-form orgs |
| **Prompts (v3.1.0)** | `prompt_system.py` | 16 role templates, level guidelines, 4-layer resolution + SELF block + feature manuals |
| **Threads (v3.1.0)** | `threads.py` + `notebooks.py` | Chat threads with debate/veto/counter-argue/consensus; dual public/hidden notebooks |
| **Tools (v3.1.0)** | `integrations.py` + `cli_deployer.py` | MCP JSON-RPC connector, server registry, external CLI probe/spawn |
| **Live Execution (v3.2.0)** | `live_execution.py` | Real LLM calls via encrypted keys; free-first ladder; independent cross-model verifier that flags SUSPECT answers and forces escalation |
| **Prompt Mgmt (v3.2.0)** | `prompt_management.py` | The prompt department: writes, grades (8 criteria), auto-upgrades to the quality bar, and version-histories every prompt |
| **API Mgmt (v3.2.0)** | `api_management.py` | Per-node token+USD budgets with 80% tripwire, rate limits + burst control, fallback switching, live spend dashboard |
| **CEO Console (v3.2.0)** | `ceo_access.py` | CEO as operator: PowerShell/shell, file creation, CLI deployment, MCP tool calls — dry-run first, fully audited, powers-gated |
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
