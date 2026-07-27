"""Auth Manager — secure API key storage, .env management, credential rotation.

Features:
- Encrypted credential storage
- .env file parsing and management
- Multiple auth methods: API key, OAuth, token
- Key rotation and expiration tracking
- Environment variable injection
"""
from __future__ import annotations
import os, json, base64, time, stat
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

AUTH_DIR = Path("memory/auth")
AUTH_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = AUTH_DIR / "credentials.json"
MASTER_KEY_FILE = AUTH_DIR / ".master_key"
ENV_FILE = Path(".env")


class AuthManager:
    """Secure auth: encrypted storage, .env management, credential rotation."""

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._credentials: dict = {}
        self._init_crypto()
        self._load_credentials()
        self._load_dotenv()

    def _init_crypto(self):
        """Initialize encryption from master key."""
        if MASTER_KEY_FILE.exists():
            key_b64 = MASTER_KEY_FILE.read_text().strip()
            self._fernet = Fernet(key_b64)
        else:
            # Generate a new key
            key = Fernet.generate_key()
            MASTER_KEY_FILE.write_text(key.decode())
            # Restrict permissions on Windows
            try:
                os.chmod(str(MASTER_KEY_FILE), stat.S_IREAD | stat.S_IWRITE)
            except Exception:
                pass
            self._fernet = Fernet(key)

    def _load_credentials(self):
        if CREDENTIALS_FILE.exists():
            try:
                encrypted = CREDENTIALS_FILE.read_bytes()
                if self._fernet:
                    decrypted = self._fernet.decrypt(encrypted)
                    self._credentials = json.loads(decrypted)
            except Exception:
                self._credentials = {}
        else:
            self._credentials = {}

    def _save_credentials(self):
        if self._fernet:
            data = json.dumps(self._credentials, indent=2)
            encrypted = self._fernet.encrypt(data.encode())
            CREDENTIALS_FILE.write_bytes(encrypted)

    def _load_dotenv(self):
        """Load .env file into os.environ."""
        if not ENV_FILE.exists():
            # Create default .env if not exists
            self._create_default_dotenv()
            return
        try:
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = value
        except Exception:
            pass

    def _create_default_dotenv(self):
        template = """# MAIK API Keys — add your keys below
# Get keys from:
# OpenAI:     https://platform.openai.com/api-keys
# Anthropic:  https://console.anthropic.com/
# Google:     https://aistudio.google.com/apikey
# OpenRouter: https://openrouter.ai/keys
# DeepSeek:   https://platform.deepseek.com/api_keys

# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...
# OPENROUTER_API_KEY=sk-or-...
# DEEPSEEK_API_KEY=sk-...
"""
        try:
            ENV_FILE.write_text(template)
        except Exception:
            pass

    # ── Credential Management ──────────────────────────────────────

    def set_api_key(self, service: str, key: str, provider: str = "") -> dict:
        """Store an API key encrypted."""
        self._credentials[service] = {
            "key": key,
            "provider": provider,
            "created": time.time(),
            "last_used": time.time(),
        }
        self._save_credentials()
        # Also set in environment
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        env_var = env_var_map.get(service, f"{service.upper()}_API_KEY")
        os.environ[env_var] = key
        return {"service": service, "stored": True}

    def get_api_key(self, service: str) -> Optional[str]:
        """Get a stored API key."""
        cred = self._credentials.get(service)
        if cred:
            cred["last_used"] = time.time()
            self._save_credentials()
            return cred["key"]
        # Fallback to environment
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        env_var = env_var_map.get(service, f"{service.upper()}_API_KEY")
        return os.environ.get(env_var)

    def remove_api_key(self, service: str) -> dict:
        """Remove a stored API key."""
        if service in self._credentials:
            del self._credentials[service]
            self._save_credentials()
            return {"service": service, "removed": True}
        return {"service": service, "removed": False, "error": "Not found"}

    def list_services(self) -> list[dict]:
        """List all stored services with metadata."""
        return [
            {
                "service": k,
                "provider": v.get("provider", ""),
                "created": v.get("created", 0),
                "last_used": v.get("last_used", 0),
                "age_days": (time.time() - v.get("created", 0)) / 86400,
            }
            for k, v in self._credentials.items()
        ]

    def has_key(self, service: str) -> bool:
        return bool(self.get_api_key(service))

    # ── .env File Management ───────────────────────────────────────

    def update_dotenv(self, updates: dict[str, str]) -> dict:
        """Update .env file with new values."""
        lines = []
        updated_keys = set(updates.keys())
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    lines.append(line)
                    continue
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        lines.append(f"{key}={updates[key]}")
                        updated_keys.discard(key)
                        continue
                lines.append(line)
        # Add new keys
        for key in updated_keys:
            lines.append(f"{key}={updates[key]}")
        ENV_FILE.write_text("\n".join(lines) + "\n")
        # Also set in environment
        for key, value in updates.items():
            os.environ[key] = value
        return {"updated": list(updates.keys())}

    # ── Key Rotation ───────────────────────────────────────────────

    def rotate_api_key(self, service: str, new_key: str) -> dict:
        """Rotate a stored API key (preserve history)."""
        old = self._credentials.get(service, {}).get("key", "")
        self._credentials[service] = {
            "key": new_key,
            "provider": self._credentials.get(service, {}).get("provider", ""),
            "created": time.time(),
            "last_used": time.time(),
            "previous_key_created": self._credentials.get(service, {}).get("created", 0),
        }
        self._save_credentials()
        return {"service": service, "rotated": True, "previous_key_exists": bool(old)}

    def get_key_age(self, service: str) -> Optional[float]:
        """Get age of key in days."""
        cred = self._credentials.get(service)
        if cred:
            return (time.time() - cred.get("created", 0)) / 86400
        return None

    # ── OAuth / Token ──────────────────────────────────────────────

    def store_oauth_token(self, service: str, token: str, provider: str = "",
                          expires_in: int = 3600) -> dict:
        """Store an OAuth token with expiry tracking."""
        self._credentials[f"oauth_{service}"] = {
            "token": token, "provider": provider,
            "created": time.time(), "expires": time.time() + expires_in,
            "type": "oauth",
        }
        self._save_credentials()
        return {"service": service, "stored": True, "expires_in": expires_in}

    def get_oauth_token(self, service: str) -> Optional[str]:
        """Get OAuth token if not expired."""
        cred = self._credentials.get(f"oauth_{service}")
        if cred and cred.get("expires", 0) > time.time():
            return cred["token"]
        return None

    def is_token_expired(self, service: str) -> bool:
        cred = self._credentials.get(f"oauth_{service}")
        if cred:
            return cred.get("expires", 0) < time.time()
        return True

    # ── Status ─────────────────────────────────────────────────────

    def status(self) -> dict:
        """Full auth status."""
        services = self.list_services()
        env_keys = {k: bool(v) for k, v in os.environ.items() if k.endswith("_API_KEY")}
        return {
            "stored_services": len(services),
            "services": services,
            "env_api_keys": env_keys,
            "has_master_key": self._fernet is not None,
            "dotenv_exists": ENV_FILE.exists(),
        }


auth = AuthManager()
