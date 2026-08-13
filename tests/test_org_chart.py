"""Phase H1+H2 tests: org chart hierarchy, deployment rules, oversight, persistence,
model binding catalog + per-node resolution."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from maik_kernel.org_chart import (NodeLevel, OrgChart, OrgChartError,
                                   OrgNode, Powers)
from maik_kernel.model_binding import BindingError, BindingStore, ModelCatalog
from maik_kernel.config import ModelTier


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def org():
    return OrgChart.default()


# ---------------- H1: hierarchy basics --------------------------------
def test_default_org_has_12_ceos(org):
    assert len(org.ceos()) == 12
    assert org.stats()["total_nodes"] == 12


def test_light_org_has_2_ceos():
    org = OrgChart.light()
    assert len(org.ceos()) == 2
    assert org.stats()["by_level"]["ceo"] == 2


def test_add_manager_under_ceo(org):
    ceo = org.ceos()[0]
    mgr = org.add_manager(ceo.uid, "Dev Manager", role="dev_lead", domain="code")
    assert mgr.level is NodeLevel.MANAGER
    assert mgr in org.reportees(ceo.uid, direct=True)
    assert ceo in org.ancestors(mgr.uid)


def test_add_agent_under_manager(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="dev")
    ag = org.add_agent(mgr.uid, "A", role="writer")
    assert ag.level is NodeLevel.AGENT
    assert ag in org.reportees(mgr.uid, direct=True)


def test_only_ceo_adds_manager(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    with pytest.raises(OrgChartError):
        org.add_manager(mgr.uid, "M2", role="y")
    with pytest.raises(OrgChartError):
        org.add_manager("nope", "M3", role="z")


def test_manager_or_ceo_adds_agent(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    ag = org.add_agent(mgr.uid, "A", role="y")
    ceo_direct = org.add_agent(org.ceos()[0].uid, "A2", role="y")
    assert ag is not None and ceo_direct is not None
    with pytest.raises(OrgChartError):
        org.add_agent(ag.uid, "A3", role="z")


def test_subagent_under_agent_only(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    ag = org.add_agent(mgr.uid, "A", role="y")
    sa = org.add_subagent(ag.uid, "S", role="helper")
    assert sa.level is NodeLevel.SUBAGENT
    assert org.chain(sa.uid)[0].level is NodeLevel.CEO
    with pytest.raises(OrgChartError):
        org.add_subagent(mgr.uid, "S2", role="helper")


def test_custom_spec_build():
    org = OrgChart.from_spec({
        "name": "rehan-org",
        "ceos": [
            {"name": "CEO1", "role": "lead", "domain": "code",
             "reports": [
                 {"name": "M1", "role": "dev_lead",
                  "agents": [{"name": "A1", "role": "writer"},
                             {"name": "A2", "role": "tester"}]}]},
            {"name": "CEO2", "role": "lead", "domain": "research"},
        ],
    })
    assert org.stats()["total_nodes"] == 5
    assert org.stats()["depth"] == 2  # CEO -> manager -> agent
    assert len(org.ceos()) == 2
    a1 = org.find("A1")
    assert [n.level for n in org.chain(a1.uid)] == [NodeLevel.CEO, NodeLevel.MANAGER, NodeLevel.AGENT]


def test_remove_reparents_children(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    ag = org.add_agent(mgr.uid, "A", role="y")
    org.remove(mgr.uid)
    assert org.node(mgr.uid) is None
    assert org.node(ag.uid).uid == ag.uid
    assert org.node(ag.uid) in org.reportees(org.ceos()[0].uid, direct=True)


def test_move_level_violation(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    ag = org.add_agent(mgr.uid, "A", role="y")
    # agent cannot be moved directly under root
    with pytest.raises(OrgChartError):
        org.move(None, ag.uid)


def test_chain_and_siblings(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M1", role="x")
    a1 = org.add_agent(mgr.uid, "A1", role="y")
    a2 = org.add_agent(mgr.uid, "A2", role="y2")
    assert [n.uid for n in org.siblings(a1.uid)] == [a2.uid]
    assert org.chain(a2.uid)[-1].name == "A2"


def test_oversight_ceo_sees_all(org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    ag = org.add_agent(mgr.uid, "A", role="y")
    vis = org.visible_to(org.ceos()[0].uid)
    assert org.ceos()[0] in vis and ag in vis
    assert org.visible_to(ag.uid) == [ag]


def test_powers_defaults(org):
    assert org.ceos()[0].powers.command_run is True
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    assert mgr.powers.screen_read is False
    ag = org.add_agent(mgr.uid, "A", role="y", commands=True)
    assert ag.powers.command_run is True and ag.powers.browser_automation is False


def test_persistence_roundtrip(tmpdir, org):
    mgr = org.add_manager(org.ceos()[0].uid, "M", role="x")
    org.add_agent(mgr.uid, "A", role="y", commands=True, files=True)
    org.add_subagent(org.find("A").uid, "S", role="h")
    org.save(tmpdir / "org.json")
    org2 = OrgChart.load(tmpdir / "org.json")
    assert org2.stats() == org.stats()
    assert org2.find("S").level is NodeLevel.SUBAGENT
    assert org2.is_ancestor(org.ceos()[0].uid, org2.find("S").uid)


# ---------------- H2: model binding -----------------------------------
def test_catalog_defaults():
    cat = ModelCatalog()
    assert "anthropic/claude-3.5-haiku" in cat.all_models()
    assert len(cat.for_tier(ModelTier.FLASH)) >= 2
    assert "anthropic" in cat.providers()


def test_binding_store_set_unset(tmpdir):
    store = BindingStore(base=tmpdir)
    b = store.set("node1", "anthropic/claude-3.5-haiku")
    assert store.get("node1").model == b.model
    store.unset("node1")
    assert store.get("node1") is None


def test_binding_requires_slash(tmpdir):
    store = BindingStore(base=tmpdir)
    with pytest.raises(BindingError):
        store.set("node1", "bad-model")


def test_resolve_binding_wins_over_tier(tmpdir):
    store = BindingStore(base=tmpdir)
    cat = ModelCatalog()
    store.set("n1", "anthropic/claude-3.5-haiku")
    assert store.resolve("n1", ModelTier.FLASH, cat) == "anthropic/claude-3.5-haiku"
    assert store.resolve("n2-unbound", ModelTier.FLASH, cat).startswith("gemini")


def test_binding_persistence(tmpdir):
    s1 = BindingStore(base=tmpdir)
    s1.set("n1", "openai/gpt-4o-mini")
    s2 = BindingStore(base=tmpdir)
    assert s2.get("n1").model == "openai/gpt-4o-mini"


def test_catalog_register_custom(tmpdir):
    store = BindingStore(base=tmpdir)
    cat = ModelCatalog()
    cat.register("local/ollama-llama3", "local", ModelTier.SMALL)
    store.set("n1", "local/ollama-llama3")
    assert store.resolve("n1", ModelTier.FLASH, cat) == "local/ollama-llama3"
