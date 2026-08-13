"""Model binding (Phase H2).

Users control exactly which provider/model each org node uses. Each node may
bind a concrete "provider/model" string (e.g. "anthropic/claude-3.5-haiku",
"openrouter/qwen/qwen-3-8b"). When bound, the executor routes that node's
work through the specific model; when unbound, the node falls back to its
tier default through the free-first provider ladder (existing behavior).

The catalog records which models are available per tier and which providers
offer them. Users can register their own provider/model pairs too.
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import ModelTier

TIER_MODELS = {
    ModelTier.FLASH: [
        ("gemini", "gemini/gemini-2.0-flash-lite-001"),
        ("openrouter", "openrouter/auto:gemini-2.0-flash-lite"),
        ("openrouter", "openrouter/google/gemini-2.0-flash"),
    ],
    ModelTier.SMALL: [
        ("openrouter", "openrouter/qwen/qwen-3-4b"),
        ("openrouter", "openrouter/qwen/qwen-3-8b"),
        ("openrouter", "openrouter/deepseek/deepseek-chat-v3-0324:free"),
    ],
    ModelTier.MEDIUM: [
        ("openrouter", "openrouter/deepseek/deepseek-chat-v3-0324:free"),
        ("openai", "openai/gpt-4o-mini"),
        ("anthropic", "anthropic/claude-3.5-haiku"),
    ],
    ModelTier.LARGE: [
        ("openrouter", "openrouter/deepseek/deepseek-r1:free"),
        ("openrouter", "openrouter/google/gemini-2.5-flash"),
        ("openai", "openai/gpt-4o"),
        ("anthropic", "anthropic/claude-3.5-sonnet"),
    ],
}


@dataclass
class ModelBinding:
    """Per-node binding of an OrgNode uid -> provider/model."""
    node_uid: str
    model: str            # "provider/model" e.g. "anthropic/claude-3.5-haiku"
    pinned: bool = True   # False = suggestion, ladder may override


class BindingError(ValueError):
    pass


class ModelCatalog:
    """Registry of known provider/model pairs with tier hints."""

    def __init__(self):
        self._lock = threading.RLock()
        self._entries: Dict[str, dict] = {}   # model -> {provider, tier}
        for tier, pairs in TIER_MODELS.items():
            for provider, model in pairs:
                self.register(model, provider, tier)

    def register(self, model: str, provider: str,
                 tier: Optional[ModelTier] = None) -> None:
        with self._lock:
            self._entries[model] = {
                "model": model, "provider": provider,
                "tier": tier.value if tier else ModelTier.MEDIUM.value,
            }

    def unregister(self, model: str) -> None:
        with self._lock:
            self._entries.pop(model, None)

    def get(self, model: str) -> Optional[dict]:
        return self._entries.get(model)

    def for_tier(self, tier: ModelTier) -> List[dict]:
        with self._lock:
            return [e for e in self._entries.values() if e["tier"] == tier.value]

    def all_models(self) -> List[str]:
        with self._lock:
            return sorted(self._entries)

    def providers(self) -> List[str]:
        with self._lock:
            return sorted({e["provider"] for e in self._entries.values()})

    def to_json(self) -> str:
        with self._lock:
            return json.dumps({"version": 1, "entries": self._entries}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "ModelCatalog":
        d = json.loads(text)
        cat = cls()
        for model, e in d.get("entries", {}).items():
            cat.register(model, e["provider"],
                         ModelTier(e["tier"]) if e.get("tier") in {t.value for t in ModelTier} else None)
        return cat


class BindingStore:
    """Per-node model bindings, persisted under MAIK_DATA_DIR."""

    def __init__(self, base: Optional[Path] = None):
        self.base = Path(base) if base else Path(
            __import__("os").environ.get("MAIK_DATA_DIR", ".")) / "bindings"
        self.base.mkdir(parents=True, exist_ok=True)
        self._path = self.base / "model_bindings.json"
        self._lock = threading.RLock()
        self._bindings: Dict[str, ModelBinding] = {}
        self._load()

    # -- core ----------------------------------------------------------
    def set(self, node_uid: str, model: str, pinned: bool = True) -> ModelBinding:
        if not model or "/" not in model:
            raise BindingError(f"Model must be provider/model, got {model!r}")
        b = ModelBinding(node_uid, model, pinned)
        with self._lock:
            self._bindings[node_uid] = b
            self._save()
        return b

    def unset(self, node_uid: str) -> None:
        with self._lock:
            self._bindings.pop(node_uid, None)
            self._save()

    def get(self, node_uid: str) -> Optional[ModelBinding]:
        return self._bindings.get(node_uid)

    def bound_nodes(self) -> Dict[str, ModelBinding]:
        return dict(self._bindings)

    def resolve(self, node_uid: str, tier: ModelTier,
                catalog: ModelCatalog) -> str:
        """Concrete model to call for a node: binding wins, else tier default."""
        b = self.get(node_uid)
        if b is not None:
            return b.model
        for e in catalog.for_tier(tier):
            return e["model"]
        # catalog empty (unlikely): fall back to a known small model
        return "openrouter/qwen/qwen-3-8b"

    def summary(self) -> dict:
        return {
            "bound": len(self._bindings),
            "bindings": {uid: {"model": b.model, "pinned": b.pinned}
                         for uid, b in self._bindings.items()},
        }

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        if self._path.exists():
            try:
                d = json.loads(self._path.read_text())
            except json.JSONDecodeError:
                return
            for uid, e in d.get("bindings", {}).items():
                self._bindings[uid] = ModelBinding(uid, e["model"], bool(e.get("pinned", True)))

    def _save(self) -> None:
        self._path.write_text(json.dumps({
            "version": 1,
            "bindings": {uid: {"model": b.model, "pinned": b.pinned}
                         for uid, b in self._bindings.items()},
        }, indent=2))
