import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")
os.environ["MAIK_STUB"] = "1"

from maik_kernel.config import Config
from maik_kernel.router import Router


def test_routing_map():
    r = Router(Config())
    cases = {
        "Calculate 7 x 8": ("math", "flash"),
        "Write a Python function for primes": ("code", "small"),
        "Explain photosynthesis": ("research", "flash"),
        "Find SQL injection vuln": ("security", "medium"),
        "Brainstorm a name for my startup": ("creative", "small"),
    }
    for p, (domain, tier) in cases.items():
        d = r.route(p)
        assert (d.ceo_domain, d.tier.value) == (domain, tier), (p, d.ceo_domain, d.tier.value)
    r.close()


def test_cache_hit_and_persistence():
    with tempfile.TemporaryDirectory() as td:
        cfg = Config()
        r1 = Router(cfg, cache_path=Path(td) / "p.db")
        a = r1.route("Calculate 12 + 9")
        b = r1.route("Calculate 15 + 3")
        assert a.cached is False and b.cached is True
        r1.close()
        # persistence: a new router loads the stored pattern
        r2 = Router(cfg, cache_path=Path(td) / "p.db")
        c = r2.route("Calculate 2 + 2")
        assert c.cached is True
        r2.close()


def test_dial_affects_threshold():
    low = Config(friction=0).friction.min_confidence
    high = Config(friction=10).friction.min_confidence
    assert low < high
