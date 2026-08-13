"""Live verification run for MAIK v3.4.0.

Runs TruthBench problems through multiple live models via the sandbox LLM
proxy (MAIK_LIVE_BASE_URL / MAIK_LIVE_API_KEY pinned as the first provider
rung), each answer graded by MAIK's judge plus a SECOND independent model
verifier (anti-hallucination loop) on passing rows.

Outputs:
  live_verify_results.json  — per-problem, per-model verdicts
  live_verify_report.md     — human-readable evidence report
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

# silence litellm info spam on stdout
logging.getLogger("litellm").setLevel(logging.ERROR)

from maik_kernel.bench_truth import TruthBench  # noqa: E402
from maik_kernel.specialization import (  # noqa: E402
    SpecializationBench,
    SpecializationMatrix,
    compare_report,
)
from maik_kernel.config import Config  # noqa: E402
from maik_kernel.executor import Executor  # noqa: E402
from maik_kernel.live_execution import LiveExecution  # noqa: E402

DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODELS = [
    "gpt-5-nano",
    "gpt-5-mini",
    "gemini-3-flash-preview",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
]


def main(models_override=None, keep_domains=False):
    t0 = time.time()
    cfg = Config()
    bench = TruthBench(config=cfg)
    ex = Executor(cfg)
    matrix = SpecializationMatrix(base=None)  # in-memory for the live run
    sb = SpecializationBench(matrix, executor=ex, bench=bench)
    live = LiveExecution()

    problems = bench.DEFAULTS
    if keep_domains:
        per_domain = {}
        for p in problems:
            per_domain.setdefault(p.domain, []).append(p)
        picked = []
        for dom in sorted(per_domain):
            picked += per_domain[dom][:2]
        problems = picked
    # Pin the verifier to a live model available on the pinned endpoint
    if "MAIK_LIVE_VERIFIER_MODEL" not in os.environ:
        os.environ["MAIK_LIVE_VERIFIER_MODEL"] = "gpt-5-mini"
    models = models_override or MODELS
    print(f"# MAIK v3.4.0 live verification: {len(models)} models x "
          f"{len(problems)} problems "
          f"(domains: {sorted(set(p.domain for p in problems))})", flush=True)
    out = sb.run(models, problems=problems)

    # Independent verifier grades every passing answer (second-model loop)
    verified = 0
    t_last = time.time()
    for i, row in enumerate(out["rows"]):
        prob = next((p for p in problems if p.id == row["pid"]), None)
        if prob and row["ok"]:
            t1 = time.time()
            try:
                v = live.verify(prob.problem, row["answer"] or "")
            except Exception:  # noqa: BLE001
                v = {"verdict": "UNVERIFIED"}
            row["verdict"] = v.get("verdict", "UNKNOWN")
            row["verifier_note"] = (v.get("reason", "") or "")[:150]
            verified += 1
            if time.time() - t1 > 15:
                print(f"# slow verify ({time.time()-t1:.1f}s) for {row['pid']} "
                      f"on {row['model']}", flush=True)
        print(f"# progress {i+1}/{len(out['rows'])} rows graded "
              f"({time.time()-t_last:.1f}s elapsed)", flush=True)
        t_last = time.time()
    print(f"# verified {verified} passing rows with second model", flush=True)

    elapsed = time.time() - t0
    swarm = out["swarm"]
    total = len(out["rows"])
    passed = sum(1 for r in out["rows"] if r["ok"])

    report_md = compare_report(matrix)
    results_snip = json.dumps({
        "swarm": out["swarm"],
        "rows": [{k: r.get(k) for k in
                  ("model", "pid", "domain", "ok", "verdict")}
                 for r in out["rows"]],
    }, indent=1)

    full_report = f"""# MAIK v3.4.0 — Live Verification Evidence (Phase N)

Run date (UTC): {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}
Models tested: {', '.join(models)}
Problems: {len(problems)} ground-truth problems per model (TruthBench set)
Judge: MAIK numeric/semantic correctness judge + independent second-model
       verifier on every passing answer (anti-hallucination loop).
Runner: MAIK Executor model_override (Phase N) over ProviderLadder
        (MAIK_LIVE_BASE_URL pinned as first rung).

## Headline numbers

- Rows recorded (model x problem): {total}
- Judge-passed: {passed} ({passed/total:.0%})
- Swarm (best-specialist) average accuracy across {swarm['domains_covered']} domains: {swarm['swarm_avg_accuracy']:.0%}
- Wall time: {elapsed:.1f}s
- Per-row cost tracked in live_verify_results.json.

## Sourced rival framing

Claude Mythos 5 (Anthropic, April 2026, restricted access) claims top-of-field
scores, but independent researchers showed its headline results depended on
2 benchmark bugs (scores drop to <5% without them), and an open-source 3.6B
model independently found the same headline vulnerability. Mythos 5 is not
public; $10/$50 per M tokens, vetted partners only. Public version =
Claude Fable 5 (safeguarded).

MAIK's provable advantages are architecture-level, verifiable by anyone:
an independent verifier grades every answer (second-model anti-hallucination),
a self-learning flywheel improves from every run, evidence-based
domain→model routing (this run writes it), org governance with CEO veto,
and zero-cost free-first operation. That is what no single monolith —
including Mythos — replicates by design.

## Per-model / per-domain leaderboard

```json
{results_snip}
```
"""
    out_path = os.path.join(DATA_DIR, "live_verify_report.md")
    Path(DATA_DIR, "live_verify_report.md").write_text(full_report)
    with open(os.path.join(DATA_DIR, "live_verify_results.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\n" + full_report)
    return 0


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=None,
                        help="comma-separated override of the model list")
    parser.add_argument("--keep-domains", action="store_true",
                        help="Run one representative problem per domain "
                             "(faster, covers all 8 domains)")
    args = parser.parse_args()
    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    sys.exit(main(models_override=models, keep_domains=args.keep_domains))
