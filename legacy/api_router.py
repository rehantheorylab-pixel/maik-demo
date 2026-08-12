"""Intelligent Multi-API Router — routes tasks to the best API model.

Architecture:
- Maintains a registry of API providers (GPT, Claude, Gemini, OpenRouter, etc.)
- Smart task classification: determines which API is best for which task
- Gemini → research, web search, data extraction
- Claude → thinking, reasoning, complex analysis
- GPT → creative, code generation, general
- DeepSeek / custom → specialized
- Automatic fallback on failure
- Usage tracking and cost optimization
"""
from __future__ import annotations
import json, os, time, hashlib, threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum

CACHE_DIR = "memory/api_cache"
CACHE_DIR_OBJ = os.path.join("memory", "api_cache")
os.makedirs(CACHE_DIR_OBJ, exist_ok=True)

ROUTING_CACHE: dict[str, dict] = {}
ROUTING_CACHE_TTL = 300  # 5 minutes


class APICapability(Enum):
    REASONING = "reasoning"
    RESEARCH = "research"
    CODE = "code"
    CREATIVE = "creative"
    MATH = "math"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    VISION = "vision"
    GENERAL = "general"


@dataclass
class APIProvider:
    """An API provider with its capabilities, cost, and current status."""
    name: str
    provider: str  # "openai", "anthropic", "google", "openrouter", "deepseek"
    model: str
    capabilities: list[APICapability] = field(default_factory=list)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    priority: int = 1  # 1 = highest
    total_tokens: int = 0
    total_calls: int = 0
    success_rate: float = 1.0
    avg_latency: float = 1.0
    last_error: str = ""

    def __post_init__(self):
        if not self.base_url:
            defaults = {
                "openai": "https://api.openai.com/v1",
                "anthropic": "https://api.anthropic.com/v1",
                "google": "https://generativelanguage.googleapis.com/v1beta",
                "openrouter": "https://openrouter.ai/api/v1",
                "deepseek": "https://api.deepseek.com/v1",
            }
            self.base_url = defaults.get(self.provider, "")


# ── Default Providers ─────────────────────────────────────────────

DEFAULT_PROVIDERS: list[APIProvider] = [
    APIProvider(
        name="claude-sonnet", provider="anthropic",
        model="claude-3-sonnet-20240229",
        capabilities=[APICapability.REASONING, APICapability.ANALYSIS, APICapability.PLANNING, APICapability.VISION],
        cost_per_1k_input=0.003, cost_per_1k_output=0.015,
        priority=1, api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    ),
    APIProvider(
        name="claude-haiku", provider="anthropic",
        model="claude-3-haiku-20240307",
        capabilities=[APICapability.GENERAL, APICapability.CODE, APICapability.ANALYSIS],
        cost_per_1k_input=0.00025, cost_per_1k_output=0.00125,
        priority=3, api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    ),
    APIProvider(
        name="gpt-4o", provider="openai",
        model="gpt-4o",
        capabilities=[APICapability.CREATIVE, APICapability.CODE, APICapability.GENERAL, APICapability.REASONING, APICapability.VISION],
        cost_per_1k_input=0.005, cost_per_1k_output=0.015,
        priority=2, api_key=os.environ.get("OPENAI_API_KEY", ""),
    ),
    APIProvider(
        name="gpt-4o-mini", provider="openai",
        model="gpt-4o-mini",
        capabilities=[APICapability.GENERAL, APICapability.CODE],
        cost_per_1k_input=0.00015, cost_per_1k_output=0.0006,
        priority=4, api_key=os.environ.get("OPENAI_API_KEY", ""),
    ),
    APIProvider(
        name="gemini-pro", provider="google",
        model="gemini-1.5-pro",
        capabilities=[APICapability.RESEARCH, APICapability.REASONING, APICapability.CODE, APICapability.VISION],
        cost_per_1k_input=0.00125, cost_per_1k_output=0.005,
        priority=3, api_key=os.environ.get("GOOGLE_API_KEY", ""),
    ),
    APIProvider(
        name="gemini-flash", provider="google",
        model="gemini-1.5-flash",
        capabilities=[APICapability.RESEARCH, APICapability.GENERAL, APICapability.VISION],
        cost_per_1k_input=0.000075, cost_per_1k_output=0.0003,
        priority=5, api_key=os.environ.get("GOOGLE_API_KEY", ""),
    ),
    APIProvider(
        name="deepseek-coder", provider="deepseek",
        model="deepseek-coder-33b-instruct",
        capabilities=[APICapability.CODE, APICapability.MATH, APICapability.REASONING],
        cost_per_1k_input=0.00014, cost_per_1k_output=0.00014,
        priority=4, api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    ),
    # OpenRouter: gateway to many models
    APIProvider(
        name="openrouter-auto", provider="openrouter",
        model="mistralai/mixtral-8x22b-instruct",
        capabilities=[APICapability.GENERAL, APICapability.CODE],
        cost_per_1k_input=0.0009, cost_per_1k_output=0.0009,
        priority=5, api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    ),
]

# ── Task → Capability Mapping ─────────────────────────────────────

TASK_CAPABILITY_MAP: dict[str, APICapability] = {
    "research": APICapability.RESEARCH, "web_search": APICapability.RESEARCH,
    "reasoning": APICapability.REASONING, "logic": APICapability.REASONING,
    "code": APICapability.CODE, "programming": APICapability.CODE,
    "creative": APICapability.CREATIVE, "writing": APICapability.CREATIVE,
    "math": APICapability.MATH, "calculation": APICapability.MATH,
    "analysis": APICapability.ANALYSIS, "evaluate": APICapability.ANALYSIS,
    "plan": APICapability.PLANNING, "planning": APICapability.PLANNING,
    "image": APICapability.VISION, "vision": APICapability.VISION,
    "general": APICapability.GENERAL,
}


class IntelligentRouter:
    """Routes tasks to the best API based on task type, cost, and availability.

    Key features:
    - Smart task classification → capability mapping
    - Gemini → research tasks (best web grounding)
    - Claude → reasoning/thinking tasks (best structured thinking)
    - GPT → creative/code tasks (best general purpose)
    - Fallback chain on failure
    - Usage tracking per provider
    - API key management with .env support
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: list[APIProvider] = []
        self._provider_map: dict[str, APIProvider] = {}
        self._route_history: list[dict] = []
        self._load_providers()

    def _load_providers(self):
        for p in DEFAULT_PROVIDERS:
            self.add_provider(p)

    def add_provider(self, provider: APIProvider):
        with self._lock:
            self._providers.append(provider)
            self._provider_map[provider.name] = provider
            # Sort by priority
            self._providers.sort(key=lambda p: p.priority)

    def remove_provider(self, name: str):
        with self._lock:
            self._providers = [p for p in self._providers if p.name != name]
            self._provider_map.pop(name, None)

    def get_provider(self, name: str) -> Optional[APIProvider]:
        return self._provider_map.get(name)

    def list_providers(self) -> list[dict]:
        return [
            {
                "name": p.name, "provider": p.provider, "model": p.model,
                "capabilities": [c.value for c in p.capabilities],
                "enabled": p.enabled, "priority": p.priority,
                "total_calls": p.total_calls, "success_rate": round(p.success_rate, 2),
                "avg_latency": round(p.avg_latency, 2),
                "has_key": bool(p.api_key),
            }
            for p in self._providers
        ]

    def classify_task(self, task: str) -> APICapability:
        """Classify a task description into the required capability."""
        task_lower = task.lower()
        # Check for explicit capability keywords
        for keyword, capability in TASK_CAPABILITY_MAP.items():
            if keyword in task_lower:
                return capability
        # Advanced classification
        words = set(task_lower.split())
        research_words = {"research", "search", "find", "lookup", "web", "information", "data"}
        reasoning_words = {"think", "reason", "logic", "analyze", "evaluate", "compare", "why"}
        code_words = {"code", "program", "function", "implement", "debug", "compile", "test", "api"}
        creative_words = {"write", "create", "design", "story", "poem", "content", "blog", "article"}

        if words & research_words:
            return APICapability.RESEARCH
        if words & reasoning_words:
            return APICapability.REASONING
        if words & code_words:
            return APICapability.CODE
        if words & creative_words:
            return APICapability.CREATIVE
        return APICapability.GENERAL

    def route(self, task: str, domain: str = "") -> dict:
        """Route a task to the best API provider.

        Returns dict with:
        - provider: selected provider name
        - capability: mapped capability
        - model: model name
        - priority: priority level
        - fallback_chain: ordered list of fallback providers
        """
        capability = self.classify_task(task)
        with self._lock:
            available = [
                p for p in self._providers
                if p.enabled and p.api_key and capability in p.capabilities
            ]
            if not available:
                # Try any enabled provider
                available = [p for p in self._providers if p.enabled and p.api_key]
            if not available:
                return {
                    "provider": "", "capability": capability.value,
                    "model": "", "error": "No available provider for capability",
                    "priority": 0, "fallback_chain": [],
                }
            # Best: highest priority + highest success rate
            best = max(available, key=lambda p: (p.priority, p.success_rate))
            fallback = [p for p in available if p.name != best.name]
            self._route_history.append({
                "time": time.time(),
                "task": task[:80], "capability": capability.value,
                "selected": best.name, "fallbacks": [f.name for f in fallback[:3]],
            })
            return {
                "provider": best.name,
                "provider_type": best.provider,
                "model": best.model,
                "capability": capability.value,
                "priority": best.priority,
                "cost_per_1k_input": best.cost_per_1k_input,
                "cost_per_1k_output": best.cost_per_1k_output,
                "fallback_chain": [f.name for f in fallback[:5]],
                "base_url": best.base_url,
            }

    def call(self, task: str, system_prompt: str = "", domain: str = "",
             max_tokens: int = 2000, temperature: float = 0.7) -> dict:
        """Route AND call the best API for a task. Full end-to-end."""
        result = self.route(task, domain)
        provider_name = result.get("provider", "")
        if not provider_name:
            return {"error": result.get("error", "No provider"), "success": False}
        provider = self.get_provider(provider_name)
        if provider is None:
            return {"error": f"Provider '{provider_name}' not found", "success": False}

        # Try the selected provider, then fallback chain
        chain = [provider_name] + result.get("fallback_chain", [])
        last_error = ""
        for pname in chain:
            p = self.get_provider(pname)
            if p is None or not p.enabled or not p.api_key:
                continue
            try:
                resp = self._do_call(p, system_prompt or task, task, max_tokens, temperature)
                # Update stats
                with self._lock:
                    p.total_calls += 1
                    p.total_tokens += resp.get("total_tokens", 0)
                    p.avg_latency = (p.avg_latency * 0.9 + resp.get("latency", 1.0) * 0.1)
                    p.success_rate = p.success_rate * 0.95 + 0.05
                return {
                    "success": True,
                    "provider": p.name, "model": p.model,
                    "content": resp.get("content", ""),
                    "total_tokens": resp.get("total_tokens", 0),
                    "latency": resp.get("latency", 0),
                    "tokens_in": resp.get("tokens_in", 0),
                    "tokens_out": resp.get("tokens_out", 0),
                    "cached": resp.get("cached", False),
                }
            except Exception as e:
                last_error = str(e)
                with self._lock:
                    p.last_error = str(e)[:200]
                continue
        return {"error": last_error, "success": False, "provider": chain[0]}

    def _do_call(self, provider: APIProvider, system_prompt: str, user_message: str,
                 max_tokens: int, temperature: float) -> dict:
        """Execute the actual API call for the given provider."""
        start = time.time()
        cache_key = hashlib.md5(
            f"{provider.name}:{system_prompt[:200]}:{user_message[:200]}:{max_tokens}".encode()
        ).hexdigest()
        # Check cache
        cache_path = os.path.join(CACHE_DIR_OBJ, f"{cache_key}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    cached = json.load(f)
                    if time.time() - cached.get("ts", 0) < CACHE_DIR and cached.get("prompt") == system_prompt[:200]:
                        cached["cached"] = True
                        cached["latency"] = time.time() - start
                        return cached
            except Exception:
                pass
        if provider.provider in ("openai", "openrouter"):
            return self._call_openai(provider, system_prompt, user_message, max_tokens, temperature, cache_key, start)
        elif provider.provider == "anthropic":
            return self._call_anthropic(provider, system_prompt, user_message, max_tokens, temperature, cache_key, start)
        elif provider.provider == "google":
            return self._call_google(provider, system_prompt, user_message, max_tokens, temperature, cache_key, start)
        elif provider.provider == "deepseek":
            # DeepSeek uses OpenAI-compatible API
            return self._call_openai(provider, system_prompt, user_message, max_tokens, temperature, cache_key, start)
        else:
            return {"error": f"Unknown provider: {provider.provider}", "content": ""}

    def _call_openai(self, provider: APIProvider, system_prompt: str, user_message: str,
                     max_tokens: int, temperature: float, cache_key: str, start: float) -> dict:
        import requests
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful AI assistant."},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(
            f"{provider.base_url}/chat/completions",
            headers=headers, json=body, timeout=60,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise Exception(f"OpenAI API error: {data}")
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        elapsed = time.time() - start
        result = {
            "content": choice["content"], "total_tokens": usage.get("total_tokens", 0),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency": elapsed, "cached": False, "prompt": system_prompt[:200],
        }
        # Cache
        try:
            with open(os.path.join(CACHE_DIR_OBJ, f"{cache_key}.json"), "w") as f:
                json.dump({**result, "ts": time.time()}, f)
        except Exception:
            pass
        return result

    def _call_anthropic(self, provider: APIProvider, system_prompt: str, user_message: str,
                        max_tokens: int, temperature: float, cache_key: str, start: float) -> dict:
        import requests
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": provider.model,
            "system": system_prompt or "You are a helpful AI assistant.",
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(
            f"{provider.base_url}/messages",
            headers=headers, json=body, timeout=60,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise Exception(f"Anthropic API error: {data}")
        content = data.get("content", [{}])[0].get("text", "")
        usage = data.get("usage", {})
        elapsed = time.time() - start
        result = {
            "content": content, "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            "tokens_in": usage.get("input_tokens", 0),
            "tokens_out": usage.get("output_tokens", 0),
            "latency": elapsed, "cached": False, "prompt": system_prompt[:200],
        }
        try:
            with open(os.path.join(CACHE_DIR_OBJ, f"{cache_key}.json"), "w") as f:
                json.dump({**result, "ts": time.time()}, f)
        except Exception:
            pass
        return result

    def _call_google(self, provider: APIProvider, system_prompt: str, user_message: str,
                     max_tokens: int, temperature: float, cache_key: str, start: float) -> dict:
        import requests
        url = f"{provider.base_url}/models/{provider.model}:generateContent?key={provider.api_key}"
        body = {
            "contents": [{
                "parts": [{"text": user_message}],
                "role": "user",
            }],
            "systemInstruction": {"parts": [{"text": system_prompt or "You are a helpful AI assistant."}]},
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        resp = requests.post(url, json=body, timeout=60)
        data = resp.json()
        if resp.status_code != 200:
            raise Exception(f"Google API error: {data}")
        candidates = data.get("candidates", [])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = " ".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        elapsed = time.time() - start
        result = {
            "content": content,
            "total_tokens": usage.get("totalTokenCount", 0),
            "tokens_in": usage.get("promptTokenCount", 0),
            "tokens_out": usage.get("candidatesTokenCount", 0),
            "latency": elapsed, "cached": False, "prompt": system_prompt[:200],
        }
        try:
            with open(os.path.join(CACHE_DIR_OBJ, f"{cache_key}.json"), "w") as f:
                json.dump({**result, "ts": time.time()}, f)
        except Exception:
            pass
        return result

    def stats(self) -> dict:
        with self._lock:
            total_calls = sum(p.total_calls for p in self._providers)
            total_tokens = sum(p.total_tokens for p in self._providers)
            return {
                "providers": len(self._providers),
                "enabled": sum(1 for p in self._providers if p.enabled),
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "history_size": len(self._route_history),
                "api_keys_set": sum(1 for p in self._providers if p.api_key),
            }

    def history(self, limit: int = 20) -> list[dict]:
        return self._route_history[-limit:]

    def optimize_routing(self):
        """Auto-adjust priorities based on recent success rates and latency."""
        with self._lock:
            for p in self._providers:
                if p.total_calls > 0:
                    # Boost fast + reliable providers
                    p.priority = max(1, int(
                        (1.0 - p.avg_latency / 10) * 5 * p.success_rate
                    ))
            self._providers.sort(key=lambda p: p.priority)


router = IntelligentRouter()
