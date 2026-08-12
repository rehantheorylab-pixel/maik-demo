"""Provider ladder — upgrade U1: LLM calls never die silently.

Ordered list of providers; each call tries them in order with automatic
failover on auth (401), rate (429), or timeout errors. Each provider has an
independent circuit breaker (fail-N-times -> open for cooldown).

Model names are litellm strings resolved against the active provider:
  - OpenRouter free models: "openrouter/<model>"
  - Custom gateway (OpenAI-compatible): "openai/<model>" with base_url
  - Direct providers via litellm: "openai/<model>", "anthropic/<model>"...
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .secrets import all_secrets, get_secret

# Real cost per 1M tokens (input, output) in USD — free models cost ~0.
COST_PER_1M = {
    "gemini-2.0-flash-lite": (0.0075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "qwen-3-4b": (0.0, 0.0),  # free on openrouter
    "qwen-3-8b": (0.0, 0.0),
    "deepseek-chat-v3-0324": (0.0, 0.0),
    "deepseek-r1": (0.0, 0.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-sonnet-4-5": (3.00, 15.00),
}


def _estimate_cost(model_hint: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Cost ledger (U3): estimate USD for this call."""
    for hint, (pin, pout) in COST_PER_1M.items():
        if hint in model_hint:
            return (pin * prompt_tokens + pout * completion_tokens) / 1_000_000
    return 0.0  # unknown model assumed free (free-tier default)


@dataclass
class ProviderEntry:
    name: str
    model_prefix: str          # litellm prefix, e.g. "openrouter"
    base_url: Optional[str]    # None = default
    api_key_getter: Optional[callable]
    extra_headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; half-opens after cooldown."""

    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self._last_fail = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self.failures < self.threshold:
                return True
            if time.time() - self._last_fail > self.cooldown:
                self.failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            self._last_fail = time.time()

    @property
    def state(self) -> str:
        return "open" if self.failures >= self.threshold else "closed"


class ProviderLadder:
    """Try providers in order until one answers."""

    def __init__(self):
        self.entries: List[ProviderEntry] = []
        self.breakers: Dict[str, CircuitBreaker] = {}
        self._build_ladder()

    def _build_ladder(self) -> None:
        """Free-first ladder. Gates (custom/local/OpenRouter) before paid keys."""
        gw_url = get_secret("MAIK_GATEWAY_URL")
        gw_key = get_secret("MAIK_GATEWAY_KEY")
        free_url = get_secret("MAIK_FREE_GATEWAY_URL")
        free_key = get_secret("MAIK_FREE_GATEWAY_KEY")
        free_headers: Dict[str, str] = {}
        if get_secret("MAIK_FREE_EXTRA_HEADERS"):
            try:
                free_headers = json.loads(get_secret("MAIK_FREE_EXTRA_HEADERS"))
            except (ValueError, TypeError):
                pass
        or_key = get_secret("OPENROUTER_API_KEY")
        openai_key = get_secret("OPENAI_API_KEY")
        anthropic_key = get_secret("ANTHROPIC_API_KEY")
        google_key = get_secret("GOOGLE_API_KEY")

        self.entries = [
            ProviderEntry("local_gateway", "openai", gw_url, lambda: gw_key)
            if gw_url else None,
            ProviderEntry("free_gateway", "openai", free_url, lambda: free_key,
                          extra_headers=free_headers)
            if free_url else None,
            ProviderEntry("openrouter_free", "openrouter", None, lambda: or_key or "free"),
            ProviderEntry("openai", "openai", None, lambda: openai_key)
            if openai_key else None,
            ProviderEntry("anthropic", "anthropic", None, lambda: anthropic_key)
            if anthropic_key else None,
            ProviderEntry("google", "gemini", None, lambda: google_key)
            if google_key else None,
        ]
        self.entries = [e for e in self.entries if e is not None]
        if not self.entries:
            # absolute fallback: openrouter free models with litellm default
            self.entries = [ProviderEntry("openrouter_free", "openrouter", None, lambda: "free")]
        # MAIK_STUB=1: prepend deterministic local stand-in (offline testing)
        if os.environ.get("MAIK_STUB", "0") == "1":
            self.entries.insert(0, ProviderEntry("stub", "stub", None, None))
        for e in self.entries:
            self.breakers[e.name] = CircuitBreaker()

    def active_providers(self) -> List[ProviderEntry]:
        return [e for e in self.entries if e.enabled and self.breakers[e.name].allow()]

    def call(self, model: str, messages: List[dict], temperature: float = 0.2,
             max_tokens: int = 2048) -> dict:
        """Return {content, provider, model_used, prompt_tokens, completion_tokens, cost_usd}
        or raise the last exception if every provider fails."""
        import litellm
        litellm.drop_params = True
        litellm.set_verbose = False
        errors = []
        for entry in self.active_providers():
            breaker = self.breakers[entry.name]
            full_model = f"{entry.model_prefix}/{model}" if not model.startswith(entry.model_prefix) else model
            if entry.name == "stub":
                from .stub_provider import stub_call
                breaker.record_success()
                resp = stub_call(model, messages, temperature, max_tokens)
                return resp
            kwargs = dict(
                model=full_model, messages=messages, temperature=temperature,
                max_tokens=max_tokens, timeout=45,
            )
            if entry.base_url:
                kwargs["api_base"] = entry.base_url
            key = entry.api_key_getter() if entry.api_key_getter else None
            if key:
                kwargs["api_key"] = key
            if entry.extra_headers:
                kwargs["extra_headers"] = entry.extra_headers
            try:
                resp = litellm.completion(**kwargs)
                breaker.record_success()
                choice = resp.choices[0].message.content or ""
                usage = resp.usage
                pt = usage.prompt_tokens if usage else 0
                ct = usage.completion_tokens if usage else 0
                return {
                    "content": choice, "provider": entry.name,
                    "model_used": full_model,
                    "prompt_tokens": pt, "completion_tokens": ct,
                    "cost_usd": _estimate_cost(model, pt, ct),
                }
            except Exception as e:  # noqa: BLE001
                breaker.record_failure()
                errors.append(f"{entry.name}: {type(e).__name__}: {str(e)[:150]}")
                continue
        raise RuntimeError("All providers failed: " + " | ".join(errors))

    def status(self) -> List[dict]:
        return [
            {"provider": e.name, "prefix": e.model_prefix,
             "enabled": e.enabled,
             "circuit": self.breakers[e.name].state,
             "failures": self.breakers[e.name].failures}
            for e in self.entries
        ]
