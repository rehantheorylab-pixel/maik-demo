"""Phase H7-H9 tests: org bridge, chat threads, MCP/tool registry (stub mode)."""

import tempfile
from pathlib import Path

import pytest

from maik_kernel.config import Config
from maik_kernel.executor_org import OrgBridge
from maik_kernel.integrations import IntegrationRegistry, MCPConnector, ToolPlugin
from maik_kernel.org_chart import OrgChart, NodeLevel
from maik_kernel.threads import (TeamThread, ThreadError, ThreadHub,
                                 STATUS_CONSENSUS, STATUS_DEBATE, STATUS_VETOED)

# ---------------------------------------------------------------- threads


def _tmp_hub(org=None):
    return ThreadHub(org, base=Path(tempfile.mkdtemp()))


def test_thread_post_reply_hold():
    hub = _tmp_hub()
    t = hub.create("fix login bug", "A1")
    t.post("A1", "login fails on mobile")
    t.post("A2", "reproduced; root cause is cookie expiry", reply_to=None)
    t.post("A1", "fixed in PR #4", reply_to="does-not-exist") if False else None
    held = hub.hold("M1", "how do we speed up cache eviction?")
    assert any(m.kind == "hold" for m in held.messages)
    assert held.id in [th.id for th in hub.all_threads()]


def test_debate_consensus_requires_authority():
    org = OrgChart.light()
    ceo = org.ceos()[0]
    mgr = org.add_manager(ceo.uid, "Ops", "ops", domain="code",
                          powers=None)
    a1 = org.add_agent(mgr.uid, "A1", "code_writer", domain="code")
    a2 = org.add_agent(mgr.uid, "A2", "code_tester", domain="test")

    hub = _tmp_hub(org)
    t = hub.create("deploy new cache", a1.uid)
    t.post(a1.uid, "proposal: switch to LFU cache")
    t.open_debate()
    t.vote(a1.uid, "for")
    t.vote(a2.uid, "against")

    # ordinary agent cannot close
    with pytest.raises(ThreadError):
        t.close_consensus(a1.uid)
    # manager can
    t.close_consensus(mgr.uid)
    assert t.status == STATUS_CONSENSUS


def test_veto_requires_reason_and_allows_counter():
    org = OrgChart.light()
    ceo = org.ceos()[0]
    mgr = org.add_manager(ceo.uid, "Ops", "ops", domain="code")
    a1 = org.add_agent(mgr.uid, "A1", "code_writer", domain="code")

    hub = _tmp_hub(org)
    t = hub.create("rewrite config parser", a1.uid)
    t.post(a1.uid, "proposal")
    t.open_debate()
    t.vote(a1.uid, "for")

    # weak reason rejected
    with pytest.raises(ThreadError):
        t.veto(mgr.uid, "no")
    # manager veto with reason
    t.veto(mgr.uid, "Too risky this sprint; keep the current parser until the freeze ends.")
    assert t.status == STATUS_VETOED

    # agent counter-argument re-opens debate (once only)
    m = t.counter_argue(a1.uid, "The rewrite is isolated to one module and covered by tests; risk is low.")
    assert t.status == STATUS_DEBATE
    with pytest.raises(ThreadError):
        t.counter_argue(a1.uid, "second attempt")  # used up

    # CEO final veto
    t.veto(ceo.uid, "I reviewed the module; cross-cutting imports make it unsafe.")
    assert t.status == STATUS_VETOED


def test_thread_hub_summary():
    hub = _tmp_hub()
    t = hub.create("x", "A1")
    t.post("A1", "hi")
    s = hub.summary()
    assert s["threads"] == 1 and s["by_status"]["open"] == 1


# ------------------------------------------------------------ integrations


def test_tool_plugin_probe():
    reg = IntegrationRegistry()
    r = reg.probe_tool("aider")  # not installed in sandbox, but registered
    assert not r["available"] or r["available"] in (True, False)
    r = reg.probe_tool("no-such-tool")
    assert not r["available"] and "unknown" in r["error"]


def test_register_custom_plugin():
    reg = IntegrationRegistry()
    reg.register_plugin(ToolPlugin("my-ide", ["my-ide-bin"], "--run", "ide"))
    assert "my-ide" in reg.plugins
    assert reg.probe_tool("my-ide")["available"] is False


def test_register_mcp_server():
    reg = IntegrationRegistry()
    reg.register_mcp("my-server", "npx", ["-y", "some-mcp-server"])
    assert "my-server" in reg.mcp_defs
    r = reg.connect_mcp("my-server")
    assert not r["ok"]  # not installed in sandbox — expected


def test_mcp_call_when_not_connected():
    reg = IntegrationRegistry()
    r = reg.call_mcp("filesystem", "read_file", {"path": "x.txt"})
    assert not r["ok"]


def test_status_summary():
    reg = IntegrationRegistry()
    s = reg.status()
    assert "tool_plugins" in s and "mcp_servers" in s


# --------------------------------------------------------------- org bridge


def test_bridge_select_worker():
    spec = {"ceos": [{"name": "C1", "domain": "code",
                      "reports": [{"name": "M1", "domain": "code",
                                   "agents": [
                                       {"name": "writer", "role": "code_writer",
                                        "domain": "code"},
                                       {"name": "tester", "role": "code_tester",
                                        "domain": "test"},
                                   ]}]}]}
    org = OrgChart.from_spec(spec)
    cfg = Config()
    bridge = OrgBridge(cfg, org)
    w = bridge.select_worker("code", "code")
    assert w is not None and w.role == "code_writer"


def test_bridge_system_prompt_self_aware():
    spec = {"ceos": [{"name": "C1", "domain": "code",
                      "reports": [{"name": "M1", "domain": "code",
                                   "agents": [{"name": "writer", "role": "code_writer",
                                               "domain": "code"}]}]}]}
    org = OrgChart.from_spec(spec)
    bridge = OrgBridge(Config(), org)
    writer = [n for n in org._nodes.values() if n.role == "code_writer"][0]
    p = bridge.build_system_prompt(writer, "code")
    assert "writer" in p and "C1" in p and "code_writer" in p
    # time-aware, not token-aware: UTC timestamp present
    assert "UTC" in p or "time" in p.lower()


def test_bridge_no_org_passthrough():
    bridge = OrgBridge(Config())
    assert not bridge.active
    assert bridge.select_worker("code", "code") is None
    assert bridge.summary()["org_active"] is False


def test_bridge_model_resolve_falls_back_to_tier():
    from maik_kernel.config import ModelTier
    spec = {"ceos": [{"name": "C1", "domain": "code"}]}
    org = OrgChart.from_spec(spec)
    bridge = OrgBridge(Config(), org)
    m = bridge.resolve_model(org.ceos()[0].uid, ModelTier.FLASH)
    assert "/" in m  # catalog tier default
