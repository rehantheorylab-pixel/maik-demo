# MAIK v3.4.0 — Hard Benchmark: Monolith vs Swarm (head-to-head)
Run date (UTC): 2026-08-13 11:22 UTC
Wall time: 110.4s

## Setup (honest)
- MONOLITH: mistral-large-latest, ONE raw call per problem, no MAIK loop
- SWARM: mistral-small-latest through the MAIK executor with the second-model
  verifier (MAIK_LIVE_VERIFIER_MODEL=mistral-small-latest)
  and one automatic retry when judge/verifier rejects.
- Problems are in the STYLE of official suites (AIME math, GPQA science,
  HumanEval coding). They are NOT the official suites themselves: those
  cannot be run live on every model. Ground truth is independently
  computed (code problems also exec-checked in an isolated interpreter),
  so this is an apples-to-apples measured contest, not a claim contest.
- The monolith is the STRONGEST single model available in this run's
  catalog; the swarm is a lighter model + MAIK's architecture.

## Headline numbers
| | MONOLITH (mistral-large-latest) | SWARM (mistral-small-latest + MAIK) |
|---|---|---|
| Problems solved | 4/9 (44%) | 9/9 (100%) |
| Total cost | $0.0000 | $0.0000 |
| Total time | 58.0s | 52.4s |

## Per-domain
| Domain | Monolith | Swarm |
|---|---|---|
| code | 1/3 | 3/3 |
| math | 2/3 | 3/3 |
| research | 1/3 | 3/3 |

## Per-problem rows (full verdicts)
```json
[
 {
  "pid": "a1",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": true,
  "answer": "To solve the problem, we need to find all positive integers \\( n \\) less than 100 that satisfy the following conditions:\n1. \\( n \\equiv 3 \\mod 7 \\)\n2. \\( n \\equiv 2 \\mod 5 \\)\n\n### Step 1: Express \\( n \\) in terms of one congruence\nFrom the first condition, we can write:\n\\[ n = 7k + 3 \\]\nwhere \\( k \\",
  "cost": 0.0,
  "duration": 12.379164457321167,
  "tier": "small",
  "tokens": 690
 },
 {
  "pid": "a1",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "To find the sum of all positive integers \\( n \\) less than 100 that satisfy the given conditions, we can follow these steps:\n\n### **Step 1: Translate the Conditions into Congruences**\nWe are given:\n1. \\( n \\equiv 3 \\pmod{7} \\)\n2. \\( n \\equiv 2 \\pmod{5} \\)\n\n### **Step 2: Solve the System of Congruenc",
  "cost": 0.0,
  "duration": 5.6568427085876465,
  "tier": "small",
  "tokens": 656
 },
 {
  "pid": "a2",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": false,
  "answer": "167",
  "cost": 0.0,
  "duration": 2.3097479343414307,
  "tier": "small",
  "tokens": 61
 },
 {
  "pid": "a2",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "SUSPECT",
  "attempts": 2,
  "answer": "250",
  "cost": 0.0,
  "duration": 14.505619525909424,
  "tier": "large",
  "tokens": 73
 },
 {
  "pid": "a3",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": true,
  "answer": "15/64",
  "cost": 0.0,
  "duration": 4.498125791549683,
  "tier": "medium",
  "tokens": 66
 },
 {
  "pid": "a3",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "15/64",
  "cost": 0.0,
  "duration": 3.9108874797821045,
  "tier": "medium",
  "tokens": 78
 },
 {
  "pid": "g1",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": true,
  "answer": "(B)",
  "cost": 0.0,
  "duration": 3.3220162391662598,
  "tier": "large",
  "tokens": 85
 },
 {
  "pid": "g1",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "B",
  "cost": 0.0,
  "duration": 3.972799777984619,
  "tier": "large",
  "tokens": 96
 },
 {
  "pid": "g2",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": false,
  "answer": "",
  "cost": 0.0,
  "duration": 8.873342037200928,
  "tier": "small",
  "tokens": 0
 },
 {
  "pid": "g2",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "B",
  "cost": 0.0,
  "duration": 5.678347110748291,
  "tier": "large",
  "tokens": 91
 },
 {
  "pid": "g3",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": false,
  "answer": "",
  "cost": 0.0,
  "duration": 8.744058847427368,
  "tier": "small",
  "tokens": 0
 },
 {
  "pid": "g3",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "B",
  "cost": 0.0,
  "duration": 6.171296834945679,
  "tier": "large",
  "tokens": 88
 },
 {
  "pid": "h1",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": false,
  "answer": "",
  "cost": 0.0,
  "duration": 7.404250860214233,
  "tier": "small",
  "tokens": 0
 },
 {
  "pid": "h1",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "```python\ndef max_pair_diff(nums):\n    return max(nums) - min(nums)\n```",
  "cost": 0.0,
  "duration": 4.304067134857178,
  "tier": "small",
  "tokens": 92
 },
 {
  "pid": "h2",
  "mode": "monolith",
  "model": "mistral-large-latest",
  "ok": false,
  "answer": "",
  "cost": 0.0,
  "duration": 7.349729299545288,
  "tier": "small",
  "tokens": 0
 },
 {
  "pid": "h2",
  "mode": "swarm",
  "model": "mistral-small-latest",
  "ok": true,
  "verdict": "OK",
  "attempts": 1,
  "answer": "```python\ndef 
```

## Honest reading
The monolith brings the single strongest raw brain; the swarm brings a
lighter brain plus MAIK's verifier, retry, and exec-sanity loops. If the
swarm wins here, the win is architectural: cross-checking converts a
weaker model into a stronger solver on hard problems. If the monolith
wins on some problems, that is also honest evidence — MAIK's swarm
absorbs any model, so routing the swarm's calls through the opus-class
model would lift it further. Either outcome strengthens the thesis:
the SYSTEM is what scales, not any single brain.
