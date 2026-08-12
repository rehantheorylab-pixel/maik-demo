import sys

sys.path.insert(0, "/home/ubuntu/maik-kernel")
from maik_kernel.blackboard import Blackboard


def test_put_get():
    bb = Blackboard()
    bb.put("k1", 42, agent="a")
    assert bb.get("k1") == 42


def test_internal_hidden():
    bb = Blackboard()
    bb.note("k1", "secret", agent="a")
    bb.put("k1", "pub", agent="a")
    assert bb.get("k1") == "pub"
    assert bb.get("k1", "internal") == "secret"


def test_eviction():
    bb = Blackboard(cap=10)
    for i in range(15):
        bb.put(f"k{i}", i, agent="a", confidence=0.2 if i < 5 else 0.9)
    assert len(bb) == 10


def test_snapshot_restore():
    bb = Blackboard()
    bb.put("k", "v", agent="a")
    snap = bb.snapshot()
    bb2 = Blackboard()
    bb2.restore(snap)
    assert bb2.get("k") == "v"


def test_subscribe():
    bb = Blackboard()
    got = []
    bb.subscribe(r"task:.*", lambda e: got.append(e.key))
    bb.put("task:1", "x", agent="a")
    bb.put("other:1", "y", agent="a")
    assert got == ["task:1"]
