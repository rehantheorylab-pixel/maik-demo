import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")
os.environ["MAIK_STUB"] = "1"

from maik_kernel.config import Config
from maik_kernel.executor import Executor
from maik_kernel.pattern_lib import PatternLibrary


def _build():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    exc = Executor(Config(), pattern_lib=lib)
    return exc, lib


def test_pattern_prefix_injected():
    exc, lib = _build()
    res = exc.execute("Calculate 17 x 23")
    # exact_arith pattern matched → system message carried "Answer with only the final number"
    assert res.answer.strip() == "391"
    names = [n for n in lib.status() if n["active"]]
    assert any(n["name"] == "exact_arith" for n in names)


def test_pattern_tier_hint_applied():
    exc, lib = _build()
    res = exc.execute("Explain why the sky is blue")
    assert res.notes and res.notes[0]["event"] == "matched"
    assert res.notes[0]["pattern"] == "chain_of_thought"
    # chain_of_thought hint = small → no escalation from small tier
    assert res.tier_used.value == "small"


def test_pattern_record_updates():
    exc, lib = _build()
    exc.execute("Calculate 5 x 5")
    p = lib.patterns["exact_arith"]
    assert p.hits == 1 and p.success == 1
