"""Phase I tests: live execution with encrypted keys, verifier, key hygiene."""

import os
import tempfile
from pathlib import Path

from maik_kernel.live_execution import (FREE_TIER_MODELS, LiveExecution,
                                        _resolve_free_model)


def _stub_env():
    env = dict(os.environ, MAIK_STUB="1",
               MAIK_DATA_DIR=tempfile.mkdtemp())
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
              "GOOGLE_API_KEY"):
        env.pop(k, None)
    return env


def test_stub_verifier_passes_good_answer():
    le = LiveExecution()
    r = le.verify("What is 2+2", "4")
    assert r["verdict"] == "OK" and r["live"] is False
    assert r["provider"] == "stub"


def test_stub_verifier_flags_error_answers():
    le = LiveExecution()
    r = le.verify("What is 2+2", "LLM_ERROR: timeout")
    assert r["verdict"] == "SUSPECT"
    r = le.verify("What is 2+2", "")
    assert r["verdict"] == "SUSPECT"


def test_live_capable_false_in_stub_mode():
    le = LiveExecution()
    assert le.is_live_capable() is False
    st = le.status()
    assert st["stub_mode"] is True and st["live_capable"] is False


def test_free_model_resolution():
    assert _resolve_free_model("flash") == FREE_TIER_MODELS["flash"]
    assert _resolve_free_model("large") == FREE_TIER_MODELS["large"]
    assert _resolve_free_model("anthropic/claude-sonnet-4-5") == \
        "anthropic/claude-sonnet-4-5"  # explicit model passthrough


def test_complete_in_stub_mode():
    le = LiveExecution()
    r = le.complete(_resolve_free_model("small"), [
        {"role": "user", "content": "What is 3 x 7"},
    ])
    assert "content" in r and r["live"] is True
    assert "timestamp_utc" in r and "202" in r["timestamp_utc"]
    assert r["duration_s"] >= 0


def test_key_inventory_never_exposes_values():
    le = LiveExecution()
    inv = le.key_inventory()
    assert "keys" in inv and "warnings" in inv
    # only presence states, never any key material
    for v in inv["keys"].values():
        assert v in ("set", "missing")


def test_executor_uses_verifier_notes():
    from maik_kernel.config import Config
    from maik_kernel.executor import Executor
    exc = Executor(Config())
    res = exc.execute("Calculate 12 x 12")
    verdicts = [n for n in res.notes if n["agent"] == "verifier"]
    assert verdicts and verdicts[0]["verdict"] == "OK"
    assert res.answer.strip() == "144"


def test_executor_suspect_causes_escalation():
    """Force a SUSPECT verdict by monkey-patching verify; ensure the cascade
    escalates instead of accepting the suspect answer."""
    from maik_kernel.config import Config
    from maik_kernel.executor import Executor

    exc = Executor(Config())
    exc._live.verify = lambda p, a, m="small": {  # type: ignore
        "verdict": "SUSPECT", "content": "VERDICT=SUSPECT t",
        "provider": "stub", "prompt_tokens": 0, "completion_tokens": 0,
        "cost_usd": 0.0}
    res = exc.execute("Explain why the sky is blue")
    suspects = [n for n in res.notes if n.get("event") == "suspect_escalate"]
    assert suspects, "SUSPECT verdict must trigger escalation"
