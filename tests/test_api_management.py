"""Phase K tests: API/model management agent — quotas, rate limits,
fallback switching, cost monitoring."""

import time
from unittest import mock

from maik_kernel.api_management import ApiManagement, NodeQuota


def _dept() -> ApiManagement:
    return ApiManagement()


def test_quota_default_applied():
    d = _dept()
    r = d.set_quota("n1", "code-writer")
    assert r["usd_budget"] == 0.01 and r["token_budget"] == 100_000


def test_quota_custom_override():
    d = _dept()
    d.set_quota("n1", "math-solver", token_budget=5_000, usd_budget=0.001)
    dash = d.dashboard()["nodes"]
    row = next(r for r in dash if r["node"] == "math-solver")
    assert row["usd_budget"] == 0.001


def test_spend_allowed_then_denied_over_usd():
    d = _dept()
    d.set_quota("n1", "node1", usd_budget=0.01)
    r1 = d.record_spend("n1", "openrouter_free", 500, 0.006)
    assert r1["allowed"] is True
    r2 = d.record_spend("n1", "openrouter_free", 500, 0.005)
    assert r2["allowed"] is False and r2["reason"] == "usd_over"


def test_tripwire_warning_at_80_percent():
    d = _dept()
    d.set_quota("n1", "node1", usd_budget=0.01)
    r = d.record_spend("n1", "openrouter_free", 500, 0.008)
    assert r["allowed"] is True and r["warning"] == "approaching_usd_budget"


def test_tokens_over_quota_denied():
    d = _dept()
    d.set_quota("n1", "node1", token_budget=100, usd_budget=1.0)
    d.record_spend("n1", "openrouter_free", 50, 0.0)
    r = d.record_spend("n1", "openrouter_free", 60, 0.0)
    assert r["allowed"] is False and r["reason"] == "tokens_over"


def test_rate_limit_denies_burst_overflow():
    d = _dept()
    d.set_quota("n1", "node1", usd_budget=1.0, token_budget=1_000_000)
    # stub provider has burst=500; use a tight custom limit
    d._limits["stub"] = __import__("dataclasses", fromlist=["replace"]).replace(
        d._limits["stub"], calls_per_minute=4, burst=3)
    for _ in range(3):
        d.record_spend("n1", "stub", 10, 0.0)
    r = d.record_spend("n1", "stub", 10, 0.0)
    assert r["allowed"] is False and r["reason"] == "rate_limit"


def test_dashboard_aggregates_day_totals():
    d = _dept()
    d.set_quota("n1", "node1", usd_budget=1.0)
    d.record_spend("n1", "openrouter_free", 100, 0.002)
    d.record_spend("n1", "openrouter_free", 200, 0.003)
    dash = d.dashboard()
    assert dash["day_total_usd"] == 0.005
    assert dash["day_total_tokens"] == 300
    assert dash["calls_day"] == 2


def test_estimate_cost_known_and_unknown_models():
    d = _dept()
    c = d.estimate_cost("gemini-2.0-flash-lite", 1000, 1000)
    assert abs(c - (0.0075 + 0.30) / 1000) < 1e-6
    assert d.estimate_cost("unknown-model-xyz", 1000, 1000) == 0.0


def test_fallback_report_healthy_when_all_closed():
    d = _dept()
    fb = d.fallback_report()
    assert not fb["stressed_providers"]
    assert fb["reroute_advice"] == "all clear"


def test_fallback_report_detects_open_circuit():
    d = _dept()
    d.live.ladder.breakers["openrouter_free"].failures = 5
    fb = d.fallback_report()
    assert "openrouter_free" in fb["stressed_providers"]
    assert "switch" in fb["reroute_advice"]
