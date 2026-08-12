# Phase A — Foundation: Mini-Step List

Each mini-step is one small, testable unit of work. Steps marked [T] include an immediate test right after. Hard things are split small; easy things are batched. Nothing advances until the step's test passes.

## A1. Project skeleton (5 steps)
A1.1 Create maik_kernel/ package dir + __init__.py [T: import succeeds]
A1.2 requirements.txt v2 (fastapi, uvicorn, pydantic, litellm, requests, cryptography, pytest, tabulate) [T: install clean]
A1.3 .gitignore (blocks .env, *.key, __pycache__, .pytest_cache) [T: git check-ignore .env]
A1.4 secrets skeleton: .env.example template with placeholders only [T: file parses]
A1.5 pytest.ini + tests/ dir [T: pytest --collect-only]

## A2. secrets.py — encrypted env (7 steps)
A2.1 derive_key from env var + machine id fallback [T: same inputs same key]
A2.2 encrypt_file / decrypt_file round-trip [T: round-trip equals original]
A2.3 first-run: generate .env from .env.example, encrypted with derived key [T: .env exists, unreadable without key]
A2.4 get_secret(name): decrypt + decode, cache in memory 5 min [T: returns placeholder value]
A2.5 secrets audit: scan env for anything not in approved list [T: clean on fresh .env]
A2.6 handle missing key gracefully: prompt-style error, never crash whole system [T: import ok with no .env]
A2.7 document secret workflow in README section [T: manual read]

## A3. config.py — council + budgets + friction (18 steps)
A3.1 ModelTier enum (flash/small/medium/large) with example models per tier [T: members exist]
A3.2 CEOProfile dataclass: name, domain, experts, default_model, budget_tokens [T: instantiates]
A3.3 12 CEO definitions (Strategy/Code/Math/Research/Exploration/Security/Synthesis/Planning/Data/Creative/Review/Ops) [T: count == 12]
A3.4 ProfileMode enum (light=2 CEOs full) + council builder [T: light has 2, full has 12]
A3.5 Per-CEO budget ledger: used/remaining tracking [T: spend(100) reduces remaining]
A3.6 BudgetTripwire: warn at 15%, critical at 5%, deny at 0% [T: thresholds fire in order]
A3.7 FrictionDial 0-10: maps to min_confidence (0.3-0.95) and max_depth [T: dial 0/5/10 values monotonic]
A3.8 Config dataclass assembly: council+ledger+tripwire+dial+version "3.0.0" [T: default_config valid]
A3.9 Config load from JSON file [T: round-trip config↔file]
A3.10 Config validate: sane ranges, model tiers match ModelTier [T: bad file raises ConfigError]
A3.11 Per-CEO cost limits ($/task) parallel to token budget [T: set_limit + check]
A3.12 Council API: ceo_for_domain(domain) lookup by expert list [T: math domain → Math CEO]
A3.13 council_breakdown() report dict [T: keys present]
A3.14 Config hot-reload hook (callback on change) [T: callback fires]
A3.15 Freeze mode for benchmark runs (no hot-reload) [T: frozen flag on]
A3.16 Config docstring API surface [T: help(config) renders]
A3.17 Unit tests file tests/test_config.py covering A3.1-3.15 [T: pytest green]
A3.18 Perf check: config cold load < 10ms [T: timed]

## A4. blackboard.py — shared memory (8 steps)
A4.1 Blackboard class: put/get by key, thread-safe lock [T: concurrent puts safe]
A4.2 Internal notes: private channel only agents read [T: note not in public get]
A4.3 BlackboardEntry: content + agent + timestamp + confidence + visibility [T: fields round-trip]
A4.4 Subscriptions: agent subscribes to key pattern, notified on put [T: notify fires]
A4.5 Size cap + eviction (oldest low-confidence first) [T: cap honored]
A4.6 Snapshot/restore (for replay) [T: snapshot == original after restore]
A4.7 Blackboard to dict for JSON API [T: serializable]
A4.8 tests/test_blackboard.py [T: green]

## A5. router.py — CEO-aware routing + persistent pattern cache (15 steps)
A5.1 ProblemClassifier: rule-based first (regex/keyword) → code/math/research/general [T: 20 canned problems classify correctly]
A5.2 Classify confidence score (rule match strength) [T: confidence in 0..1]
A5.3 Router: problem → (CEO, expert, model tier) decision object [T: math → MathCEO+flash]
A5.4 Decision includes explanation string (why this CEO) [T: non-empty]
A5.5 PatternCache in-memory: key = normalized problem hash → cached decision [T: hit after repeat]
A5.6 Cache key design: problem_type+expert+difficulty bucket, not exact string [T: similar problems hit]
A5.7 Cache stats: hits/misses/hit_rate [T: computed correctly]
A5.8 [U5] Persist cache to SQLite (decision DB) on shutdown/interval [T: survives restart]
A5.9 Load DB at startup, restore stats [T: hit_rate continues]
A5.10 Cache decay: entries older than N days weight down [T: decay applied]
A5.11 Performance curves per pattern: success_rate per (type, tier) tracked [T: curve exists]
A5.12 Router respects config friction dial in min_confidence [T: dial change alters threshold]
A5.13 Routing API dict (matches maik-demo /v1/route shape for compatibility) [T: shape test]
A5.14 tests/test_router.py [T: green]
A5.15 Perf: route decision < 2ms [T: timed]

## A6. Phase A integration gate (4 steps)
A6.1 smoke.py: build default config → classify → route → blackboard write, one shot [T: runs]
A6.2 Config change event propagates to router (dial hot-change) [T: observed]
A6.3 Memory footprint check < 50MB at idle [T: measured]
A6.4 README Phase-A section + arch diagram (Mermaid) [T: renders]

**Phase A exit:** A6.1 green + all tests green. Then Phase B (execution engine) begins.
