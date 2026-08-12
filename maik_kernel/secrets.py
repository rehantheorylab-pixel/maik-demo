"""Encrypted .env handling for MAIK Kernel.

Design: the .env file is stored encrypted with Fernet (AES-128-CBC + HMAC).
The decryption key is derived from MAIK_KEY env var if set, else a
machine-scoped fallback (HOME path + username), so it works out of the box
but stays unreadable to casual inspection. Keys are NEVER committed:
.gitignore blocks .env; only .env.example (placeholders) goes to git.

Usage:
    from maik_kernel.secrets import get_secret, ensure_env, SecretError
    ensure_env()           # first-run: creates encrypted .env from template
    api_key = get_secret("OPENAI_API_KEY")  # decrypted string, cached
"""

import base64
import os
import threading
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

BASE = Path(__file__).resolve().parent.parent  # maik-kernel/
ENV_PATH = BASE / ".env"
EXAMPLE_PATH = BASE / ".env.example"

_cache: dict = {}
_cache_lock = threading.Lock()
_cache_ttl: float = 300  # 5 minutes


class SecretError(RuntimeError):
    pass


def _derive_key() -> bytes:
    """Derive a stable Fernet key from MAIK_KEY or a machine-local secret."""
    secret = os.environ.get("MAIK_KEY", "")
    if not secret:
        secret = f"{Path.home()}|{os.environ.get('USER', 'maik')}"
    # Stretch into 32 bytes via SHA-256 (hashlib absent from stdlib guarantee?
    # hashlib IS stdlib — use it), then urlsafe-b64-encode for Fernet.
    import hashlib
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derive_key())


def _parse_env_text(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def ensure_env() -> Path:
    """First-run setup: create an encrypted .env from .env.example if missing."""
    if ENV_PATH.exists():
        return ENV_PATH
    template = EXAMPLE_PATH.read_text() if EXAMPLE_PATH.exists() else ""
    # Strip "your-" placeholder values so nobody ships template junk.
    cleaned = "\n".join(
        line for line in template.splitlines()
        if "=" not in line or not any(p in line for p in ("your-", "PLACEHOLDER"))
    )
    try:
        ENV_PATH.write_bytes(_fernet().encrypt(cleaned.encode()))
    except OSError as e:
        raise SecretError(f"Cannot write {ENV_PATH}: {e}")
    return ENV_PATH


def decrypt_env_text() -> str:
    if not ENV_PATH.exists():
        ensure_env()
    try:
        return _fernet().decrypt(ENV_PATH.read_bytes()).decode()
    except (InvalidToken, OSError) as e:
        raise SecretError(f"Cannot decrypt {ENV_PATH} (key changed?): {e}")


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return decrypted env value for `name`. Never cached longer than TTL."""
    import time
    with _cache_lock:
        if name in _cache:
            val, ts = _cache[name]
            if time.time() - ts < _cache_ttl:
                return val
    try:
        secrets = _parse_env_text(decrypt_env_text())
    except SecretError:
        # no decrypted .env available — fall back to plain process env
        # (development/testing convenience; .env encryption remains default)
        val = os.environ.get(name, default)
        return val
    val = secrets.get(name)
    if val is None and default is not None:
        val = default
    with _cache_lock:
        _cache[name] = (val, __import__("time").time())
    return val


def all_secrets() -> dict:
    """Decrypted full env map (for providers ladder, etc.)."""
    try:
        return _parse_env_text(decrypt_env_text())
    except SecretError:
        return {}


def secrets_audit() -> list:
    """Warn about suspicious values in .env (e.g., placeholders left in)."""
    flags = []
    for k, v in all_secrets().items():
        if not v:
            flags.append(f"{k} is empty")
        elif any(p in v.lower() for p in ("your-", "placeholder", "changeme")):
            flags.append(f"{k} looks like a placeholder")
    return flags
