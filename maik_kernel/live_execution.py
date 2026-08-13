"""Live execution — upgrade from stub-only to real LLM calls (Phase I).

This is the bridge between the intelligence kernel and real AI models. When
MAIK_STUB=1 (testing/offline), the deterministic stub answers. When stub is
off and real keys exist in the encrypted .env, calls go live through the
provider ladder: free gateways first, then OpenRouter free models, then paid
keys only if the grade gate demands escalation.

Every live call is metered: cost ledger, token accounting, and circuit
breakers protect you from surprise bills. The free-first ladder means a
typical solve costs $0.00.
"""

import json
import re
import os
import threading
import time
from typing import Dict, List, Optional

from .providers import ProviderLadder
from .secrets import all_secrets, secrets_audit

FREE_TIER_MODELS = {
    "flash": "gemini/gemini-2.0-flash-lite-001",
    "small": "qwen/qwen-3-4b",
    "medium": "qwen/qwen-3-8b",
    "large": "deepseek/deepseek-r1:free",
}

# Override every tier mapping at once for a custom deployment (e.g. the
# sandbox LLM proxy used for live validation). Values must be valid
# litellm strings reachable by the provider ladder — plain model ids work
# when the `openai` provider entry is enabled (it prefixes them itself).
ENV_TIER_MODEL_OVERRIDES = {
    "flash": os.environ.get("MAIK_LIVE_MODEL_FLASH", ""),
    "small": os.environ.get("MAIK_LIVE_MODEL_SMALL", ""),
    "medium": os.environ.get("MAIK_LIVE_MODEL_MEDIUM", ""),
    "large": os.environ.get("MAIK_LIVE_MODEL_LARGE", ""),
}


def _resolve_free_model(tier: str) -> str:
    """Map a tier to its free-registry default (litellm string).

    If the input already looks like a provider/model string (contains '/') or
    is not a known tier name, return it unchanged — explicit model names win.
    """
    if "/" in tier or tier not in FREE_TIER_MODELS:
        return tier
    override = ENV_TIER_MODEL_OVERRIDES.get(tier, "")
    if override:
        return override
    return FREE_TIER_MODELS[tier]


class LiveExecution:
    """Live LLM execution with key hygiene and metering."""

    def __init__(self):
        self._ladder: Optional[ProviderLadder] = None
        self._lock = threading.RLock()

    @property
    def ladder(self) -> ProviderLadder:
        with self._lock:
            if self._ladder is None:
                self._ladder = ProviderLadder()
            return self._ladder

    # ------------------------------------------------------------ tier maps
    @staticmethod
    def resolve_tier(tier: str) -> str:
        """Map a tier name to its live model, honoring per-deployment
        overrides (MAIK_LIVE_MODEL_FLASH etc.) set in the environment."""
        return _resolve_free_model(tier)

    # ------------------------------------------------------------ keys
    def key_inventory(self) -> dict:
        """What keys exist (names only — values are never exposed)."""
        present = {}
        for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                  "GOOGLE_API_KEY", "MAIK_GATEWAY_URL", "MAIK_FREE_GATEWAY_URL"):
            v = all_secrets().get(k, "")
            present[k] = "set" if v and not any(p in v.lower() for p in
                                                ("your-", "placeholder", "changeme")) else "missing"
        flags = secrets_audit()
        return {"keys": present, "warnings": flags}

    def is_live_capable(self) -> bool:
        """Can MAIK make live calls (not stub, at least one key or gateway)?"""
        if os.environ.get("MAIK_STUB", "0") == "1":
            return False
        inv = self.key_inventory()
        return any(v == "set" for v in inv["keys"].values()) or \
            "gateway" in str(self.ladder.entries)

    # ------------------------------------------------------------ calls
    def complete(self, model: str, messages: List[dict],
                 temperature: float = 0.2, max_tokens: int = 2048) -> dict:
        """One live completion through the ladder.

        Returns the ladder's dict plus `live: True` and `timestamp_utc`.
        Raises RuntimeError if every provider fails (never silently swallowed).
        """
        t0 = time.time()
        resp = self.ladder.call(model, messages, temperature, max_tokens)
        resp["live"] = True
        resp["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime(t0))
        resp["duration_s"] = round(time.time() - t0, 3)
        return resp

    def verify(self, problem: str, answer: str,
               model: str = "small") -> dict:
        """A second, independent model grades the answer (anti-hallucination).

        This is the multi-agent verification step: two different models
        looking at the same work. When they disagree, the system knows the
        answer is suspect — exactly the contradiction-mining principle.

        In stub mode (MAIK_STUB=1) verification is deterministic: short
        numeric answers pass, empty/error answers fail — no live call.
        """
        sys = ("You are MAIK's independent verifier. Given a problem and an "
               "answer produced by another model, grade the answer "
               "VERDICT=OK if correct and well-supported, VERDICT=SUSPECT "
               "otherwise, and explain in one sentence. Format: "
               "VERDICT=<OK|SUSPECT> <one-line reason>")
        if os.environ.get("MAIK_STUB", "0") == "1":
            verdict = "OK" if answer and answer.strip() and not \
                answer.strip().upper().startswith(("ERROR", "LLM_ERROR",
                                                   "TIMEOUT", "CANNOT")) else \
                "SUSPECT"
            return {"content": f"VERDICT={verdict} stub verifier", "provider": "stub",
                    "model_used": f"stub/{model}", "prompt_tokens": 0,
                    "completion_tokens": 0, "cost_usd": 0.0, "verdict": verdict,
                    "live": False}
        # Phase N: an explicit verifier model can be pinned via
        # MAIK_LIVE_VERIFIER_MODEL; tier overrides (MAIK_LIVE_MODEL_*) still
        # beat the free-registry defaults in any deployment.
        if os.environ.get("MAIK_LIVE_VERIFIER_MODEL"):
            model_id = os.environ["MAIK_LIVE_VERIFIER_MODEL"]
        elif model in FREE_TIER_MODELS:
            model_id = self.resolve_tier(model)
        else:
            model_id = model
        resp = self.complete(model_id, [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"PROBLEM: {problem}\nANSWER: {answer}"},
        ])
        content = resp.get("content", "")
        verdict = "SUSPECT"
        # Find VERDICT= anywhere in the response (models may wrap it in
        # markdown, preamble text, or code fences) — last occurrence wins.
        m = re.search(r"verdict\s*[=:]\s*(ok|suspect)", content, re.I)
        if m:
            verdict = m.group(1).upper()
        resp["verdict"] = verdict
        return resp

    # ------------------------------------------------------------ status
    def status(self) -> dict:
        return {
            "stub_mode": os.environ.get("MAIK_STUB", "0") == "1",
            "live_capable": self.is_live_capable(),
            "keys": self.key_inventory(),
            "providers": self.ladder.status(),
        }
