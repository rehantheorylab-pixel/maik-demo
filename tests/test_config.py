import sys
import json
import pytest

sys.path.insert(0, "/home/ubuntu/maik-kernel")
from maik_kernel.config import Config, ProfileMode, ModelTier, ConfigError


def test_default_council():
    assert len(Config().ceos) == 12


def test_light_mode():
    assert len(Config(mode=ProfileMode.LIGHT).ceos) == 2


def test_friction_monotonic():
    vals = [Config(friction=i).friction.min_confidence for i in range(11)]
    assert vals == sorted(vals)
    assert vals[0] < vals[-1]


def test_budget_ledger():
    c = Config()
    ceo = c.ceos[0]
    c.budgets.spend(ceo.domain, 100, 0.01)
    assert c.budgets.remaining(ceo) == ceo.budget_tokens - 100
    bd = c.budgets.breakdown(c.ceos)
    assert bd[ceo.domain]["spent_tokens"] == 100


def test_ceo_for_domain():
    c = Config()
    assert c.ceo_for_domain("math").domain == "math"


def test_json_roundtrip():
    c = Config(friction=7)
    c2 = Config.from_json(c.to_json())
    assert c2.friction.dial == 7 and len(c2.ceos) == 12


def test_bad_config():
    with pytest.raises(ConfigError):
        Config.from_json(json.dumps({
            "version": "2.0.0", "mode": "full", "friction": 5, "ceos": []}))


def test_hot_reload_hook():
    c = Config()
    fired = []
    c.on_change(lambda cfg: fired.append(1))
    c.set_friction(8)
    assert fired and c.friction.min_confidence > 0.65


def test_freeze():
    c = Config()
    c.freeze()
    with pytest.raises(ConfigError):
        c.set_friction(9)
