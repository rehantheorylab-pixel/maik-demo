import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/maik-kernel")
from maik_kernel.pattern_lib import PatternLibrary, PatternSpec


def test_defaults_registered():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    names = [p["name"] for p in lib.status()]
    assert "exact_arith" in names and "chain_of_thought" in names


def test_routing_match_and_rank():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    lib.patterns["exact_arith"].hits = 10
    lib.patterns["exact_arith"].success = 10
    m = lib.match("Calculate 17 x 23")
    assert m[0].name == "exact_arith"


def test_hot_swap_in_place():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    lib.hot_swap("exact_arith", "Solve with extreme precision.")
    assert lib.patterns["exact_arith"].prompt_prefix == "Solve with extreme precision."


def test_deactivate_excludes_from_routing():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    lib.deactivate("exact_arith")
    assert not lib.match("Calculate 5 x 5")


def test_load_from_json_file():
    td = Path(tempfile.mkdtemp())
    (td / "spy.json").write_text(json.dumps({
        "name": "spy_pattern", "signature": r"secret|hidden",
        "domain": "security", "prompt_prefix": "Reveal hidden details.",
        "tier_hint": "medium"}))
    lib = PatternLibrary(td / "p")
    lib.load_from_file(td / "spy.json")
    assert "spy_pattern" in [p["name"] for p in lib.status()]
    assert lib.match("find the secret file")[0].name == "spy_pattern"


def test_load_from_python_adapter():
    td = Path(tempfile.mkdtemp())
    (td / "hack_adapter.py").write_text(
        "def get_spec():\n"
        "    return {'name': 'py_pattern', 'signature': r'hack|exploit',\n"
        "            'domain': 'security', 'prompt_prefix': 'Think like an attacker.',\n"
        "            'tier_hint': 'medium'}\n")
    lib = PatternLibrary(td / "p")
    lib.load_from_file(td / "hack_adapter.py")
    assert lib.match("how to hack a login")[0].name == "py_pattern"


def test_record_updates_performance():
    lib = PatternLibrary(Path(tempfile.mkdtemp()) / "p")
    for _ in range(4):
        lib.record("exact_arith", True)
    assert lib.patterns["exact_arith"].performance() > 0.5
