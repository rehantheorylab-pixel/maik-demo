"""MAIK CLI (Phase G).

Single entry point: ``maik_kernel.cli`` exposes the commands

    python -m maik_kernel.cli solve "Calculate 17 x 23"
    python -m maik_kernel.cli bench [--n N] [--stub]
    python -m maik_kernel.cli status
    python -m maik_kernel.cli init
    python -m maik_kernel.cli flywheel [--revolutions N]

`init` writes an encrypted .env from the template; `solve` runs the full
tiered cascade; `bench` runs TruthBench with correctness judging; `status`
shows the learning/memory/pattern health; `flywheel` closes the loop.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from tabulate import tabulate

from .bench_truth import TruthBench
from .config import Config
from .flywheel import Flywheel
from .learn import LearningSystem
from .memory import MemorySystem
from .pattern_lib import PatternLibrary
from .secrets import ensure_env, get_secret, secrets_audit
from .executor import Executor


def cmd_init(_args: argparse.Namespace) -> int:
    """Create an encrypted .env from the template (first-run setup)."""
    p = ensure_env()
    flags = secrets_audit()
    print(f"Encrypted .env ready at {p}")
    if flags:
        print("Warnings:")
        for f in flags:
            print("  -", f)
    else:
        print("No placeholder values detected in .env.")
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    """Run the tiered cascade on one problem and print the result."""
    cfg = Config()
    lib = PatternLibrary()
    ex = Executor(cfg, pattern_lib=lib)
    try:
        res = ex.execute(args.problem, max_tokens=args.max_tokens)
    except RuntimeError as e:
        print(f"ERROR: all providers failed — {e}")
        print("Hint: run `python -m maik_kernel.cli init` and place at least "
              "one free or paid key in the encrypted .env, or retry with "
              "MAIK_STUB=1 for offline mode.")
        return 1
    print("MAIK ANSWER")
    print("=" * 40)
    print(res.answer)
    print("=" * 40)
    print(json.dumps({k: v for k, v in res.to_dict().items()
                      if k not in ("solution",)}, indent=1))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Run the ground-truth benchmark with correctness judging."""
    stub = bool(args.stub) or os.environ.get("MAIK_STUB", "").strip() == "1"
    if stub:
        os.environ["MAIK_STUB"] = "1"
    cfg = Config()
    lib = PatternLibrary()
    mem = MemorySystem()
    learn = LearningSystem()
    bench = TruthBench(config=cfg, pattern_lib=lib, memory=mem, learn=learn)
    problems = (bench.DEFAULTS[: args.n]
                if args.n and 0 < args.n < len(bench.DEFAULTS)
                else bench.DEFAULTS)
    ex = Executor(cfg, pattern_lib=lib)
    rows = bench.run(ex)
    summary = bench.summary(rows)
    print(f"Mode: {'STUB (offline)' if stub else 'LIVE'} | "
          f"{summary['total']} problems")
    print(tabulate(
        [(r.pid, "PASS" if r.correct else "FAIL", r.tier,
          f"${r.cost_usd:.5f}", f"{r.duration_s:.2f}s",
          (r.answer[:40] + "...") if r.answer else "(none)")
         for r in rows],
        headers=["id", "result", "tier", "cost", "time", "answer"],
        tablefmt="simple"))
    print("\nSummary")
    print(json.dumps(summary, indent=1))
    print("\nLearning state")
    print(json.dumps(learn.status(), indent=1))
    return 0 if summary["accuracy"] > 0 else 1


def cmd_status(_args: argparse.Namespace) -> int:
    """Show system health: providers, learning, memory, patterns."""
    learn = LearningSystem()
    mem = MemorySystem()
    lib = PatternLibrary()
    audit = secrets_audit()
    print("Key hygiene audit:", "clean" if not audit else "; ".join(audit))
    print("\nLearning state")
    print(json.dumps(learn.status(), indent=1))
    print("\nMemory state")
    print(json.dumps(mem.status(), indent=1))
    print("\nPattern library")
    print(tabulate([(p["name"], p["domain"], p["performance"],
                     p["hits"], p["active"], p["tier_hint"])
                    for p in lib.status()],
                   headers=["pattern", "domain", "perf", "hits",
                            "active", "tier"], tablefmt="simple"))
    fw_path = Path(__file__).resolve().parent.parent / "reroute_rules.json"
    if fw_path.exists():
        d = json.loads(fw_path.read_text())
        print(f"\nFlywheel: revolution {d.get('revolution', 0)}, "
              f"{len(d.get('rules', {}))} reroute rules persisted")
    return 0


def cmd_flywheel(args: argparse.Namespace) -> int:
    """Run the closed learning loop."""
    fw = Flywheel(max_revolution=args.revolutions)
    for _ in range(args.revolutions):
        report = fw.run()
        print(f"\nRevolution {report.revolution}: "
              f"{report.accuracy_before:.3f} -> {report.accuracy_after:.3f} | "
              f"rules changed {report.rules_changed}, patterns tuned "
              f"{report.patterns_tuned}, contradictions mined "
              f"{report.contradictions_mined}")
    print("\nPersisted rules:", json.dumps(fw.reroute_rules, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maik",
        description="MAIK Kernel v3 — multi-agent orchestration CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="Solve one problem with the cascade")
    s.add_argument("problem", help="The problem text")
    s.add_argument("--max-tokens", type=int, default=2048)
    s.set_defaults(func=cmd_solve)

    b = sub.add_parser("bench", help="Run the ground-truth benchmark")
    b.add_argument("--n", type=int, default=None,
                   help="Run only the first N problems")
    b.add_argument("--stub", action="store_true",
                   help="Force offline stub mode (no LLM calls)")
    b.set_defaults(func=cmd_bench)

    st = sub.add_parser("status", help="Show system health and learning state")
    st.set_defaults(func=cmd_status)

    i = sub.add_parser("init", help="Create encrypted .env (first-run setup)")
    i.set_defaults(func=cmd_init)

    f = sub.add_parser("flywheel", help="Run the closed learning loop")
    f.add_argument("--revolutions", type=int, default=1,
                   help="Number of loop revolutions (default 1)")
    f.set_defaults(func=cmd_flywheel)

    return p


def cli(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(cli())
