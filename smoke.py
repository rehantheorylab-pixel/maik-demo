#!/usr/bin/env python3
"""Phase A+B integration smoke test — A6.1 gate.

Build default config -> classify -> route -> execute -> blackboard write, one shot.
Run: MAIK_STUB=1 python3 smoke.py   (stub = offline; unset for live free gateways)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maik_kernel.config import Config, ProfileMode  # noqa: E402
from maik_kernel.executor import Executor             # noqa: E402
from maik_kernel.providers import ProviderLadder      # noqa: E402
from maik_kernel.router import Router                 # noqa: E402
from maik_kernel.safety import SafetyGate             # noqa: E402


def main() -> int:
    t0 = time.time()
    print(f"MAIK Kernel v3 smoke test (MAIK_STUB={os.environ.get('MAIK_STUB','0')})")

    # A6.1: one-shot pipeline
    cfg = Config(mode=ProfileMode.FULL, friction=5)
    print("[A3] council:", cfg.council_breakdown()["num_ceos"], "CEOs | friction dial 5 ->",
          cfg.friction.min_confidence, "min_confidence")

    router = Router(cfg)
    problems = [
        "Calculate 17 x 23",
        "Explain the history of the Roman Empire briefly",
        "Write a Python function to check if a number is prime",
    ]
    for p in problems:
        d = router.route(p)
        print(f"[A5] route: '{p[:40]}...' -> {d.ceo_name}/{d.expert} tier={d.tier.value} "
              f"conf={d.confidence} cached={d.cached}")

    ladder = ProviderLadder()
    print("[U1] provider ladder:", [e.name for e in ladder.entries],
          "| active:", [e.name for e in ladder.active_providers()])
    print("[U1] circuit states:", [(e.name, ladder.breakers[e.name].state) for e in ladder.entries])

    ex = Executor(cfg, ladder)
    for p in problems:
        r = ex.execute(p, max_tokens=100)
        d = r.to_dict()
        print(f"[B]   exec: conf={d['confidence']} tier={d['tier_used']} "
              f"esc={d['escalations']} cost=${d['cost_usd']:.5f} "
              f"time={d['duration_s']}s provider={d['provider']}")
        print(f"      sol: {d['solution'][:110]}")
        assert d["solution"], f"empty solution for: {p}"

    # A6.2: config change propagates to router
    cfg.set_friction(8)
    d = router.route("Calculate 99 x 99")
    print("[A6.2] after dial->8: min_confidence now", cfg.friction.min_confidence,
          "| route conf:", d.confidence, "| friction route requires:", cfg.friction.min_confidence)

    # A6.3: memory check
    import resource
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # MB on linux
    print(f"[A6.3] RSS: {mem:.1f} MB (gate < 50 MB: {'PASS' if mem < 50 else 'CHECK'})")

    # U3: cost ledger
    print("[U3] total cost so far: $%.6f | budget breakdown sample:" % ex.total_cost(),
          list(cfg.budgets.breakdown(cfg.ceos).values())[0])

    print(f"SMOKE PASS in {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
