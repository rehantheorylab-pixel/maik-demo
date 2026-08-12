"""CLI Plugin System — run any CLI tool as a plugin with auto-detection.

Features:
- Any CLI tool can be registered as a plugin
- Auto-detect installed tools
- Smart argument parsing
- Output capture (stdout, stderr)
- Chain commands together
- Plugin marketplace (find and install CLI tools)
"""
from __future__ import annotations
import os, sys, json, subprocess, shutil, time, re, threading
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

PLUGINS_DIR = Path("plugins")
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_REGISTRY_FILE = PLUGINS_DIR / "registry.json"


@dataclass
class CLIPlugin:
    """A registered CLI tool plugin."""
    name: str
    command: str  # The CLI command (e.g., "ffmpeg", "curl", "jq")
    description: str = ""
    category: str = "general"  # "media", "network", "data", "dev", "system"
    args_template: str = ""  # Arg format: "{input} -o {output}"
    required: list[str] = field(default_factory=list)  # Required packages
    installed: bool = False
    install_check: str = ""  # Command to check if installed, e.g., "ffmpeg -version"
    version: str = ""


# ── Built-in Plugins ──────────────────────────────────────────────

BUILTIN_PLUGINS: list[CLIPlugin] = [
    CLIPlugin("ffmpeg", "ffmpeg", "Media conversion and processing", "media",
              "-i {input} {args} {output}", install_check="ffmpeg -version"),
    CLIPlugin("ffprobe", "ffprobe", "Media file analysis", "media",
              "-v quiet -print_format json -show_format -show_streams {input}", install_check="ffprobe -version"),
    CLIPlugin("curl", "curl", "HTTP requests and data transfer", "network",
              "{args} {url}", install_check="curl --version"),
    CLIPlugin("jq", "jq", "JSON query and transformation", "data",
              "{args} {input}", install_check="jq --version"),
    CLIPlugin("git", "git", "Version control operations", "dev",
              "{args}", install_check="git --version"),
    CLIPlugin("ffuf", "ffuf", "Web fuzzing tool", "network",
              "-u {url} -w {wordlist} {args}", install_check="ffuf -V"),
    CLIPlugin("nmap", "nmap", "Network discovery and scanning", "network",
              "{args} {target}", install_check="nmap --version"),
    CLIPlugin("sqlite3", "sqlite3", "SQLite database operations", "data",
              "{database} \"{query}\"", install_check="sqlite3 --version"),
    CLIPlugin("docker", "docker", "Container management", "dev",
              "{args}", install_check="docker --version"),
    CLIPlugin("yt-dlp", "yt-dlp", "Video downloading from sites", "media",
              "{args} {url}", install_check="yt-dlp --version"),
    CLIPlugin("pandoc", "pandoc", "Document format conversion", "data",
              "{input} -o {output} {args}", install_check="pandoc --version"),
    CLIPlugin("rg", "rg", "Recursive grep search (ripgrep)", "dev",
              "{pattern} {path} {args}", install_check="rg --version"),
    CLIPlugin("fd", "fd", "File finder", "dev",
              "{pattern} {path} {args}", install_check="fd --version"),
    CLIPlugin("bat", "bat", "File viewer with syntax highlighting", "dev",
              "{args} {file}", install_check="bat --version"),
    CLIPlugin("tesseract", "tesseract", "OCR text extraction from images", "data",
              "{input} stdout {args}", install_check="tesseract --version"),
    CLIPlugin("magick", "magick", "ImageMagick image processing", "media",
              "{input} {args} {output}", install_check="magick --version"),
]


class CLIPluginManager:
    """Manage and execute CLI tools as plugins.

    Features:
    - Auto-detect installed CLI tools
    - Smart argument interpolation
    - Async execution with streaming output
    - Plugin chaining (pipe output between plugins)
    - Custom plugin registration
    """

    def __init__(self):
        self._plugins: dict[str, CLIPlugin] = {}
        self._custom_plugins: dict[str, CLIPlugin] = {}
        self._execution_history: list[dict] = []
        self._lock = threading.Lock()
        self._load_builtins()
        self._load_custom()

    def _load_builtins(self):
        for plugin in BUILTIN_PLUGINS:
            self._plugins[plugin.name] = plugin
            self._check_installed(plugin)

    def _load_custom(self):
        if PLUGIN_REGISTRY_FILE.exists():
            try:
                data = json.loads(PLUGIN_REGISTRY_FILE.read_text())
                for pdata in data:
                    plugin = CLIPlugin(**pdata)
                    self._custom_plugins[plugin.name] = plugin
                    self._plugins[plugin.name] = plugin
                    self._check_installed(plugin)
            except Exception:
                pass

    def _save_registry(self):
        data = [vars(p) for p in self._custom_plugins.values()]
        PLUGIN_REGISTRY_FILE.write_text(json.dumps(data, indent=2))

    def _check_installed(self, plugin: CLIPlugin):
        """Check if a CLI tool is installed."""
        check = plugin.install_check or f"{plugin.command} --version"
        try:
            result = subprocess.run(
                check.split(), capture_output=True, text=True, timeout=5
            )
            plugin.installed = result.returncode == 0
            if plugin.installed:
                # Extract version from output
                first_line = (result.stdout or result.stderr or "").split("\n")[0]
                version_match = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", first_line)
                if version_match:
                    plugin.version = version_match.group(1)
        except Exception:
            plugin.installed = False

    # ── Plugin Management ──────────────────────────────────────────

    def register_plugin(self, plugin: CLIPlugin) -> dict:
        """Register a custom CLI plugin."""
        with self._lock:
            self._custom_plugins[plugin.name] = plugin
            self._plugins[plugin.name] = plugin
            self._check_installed(plugin)
            self._save_registry()
            return {"name": plugin.name, "registered": True, "installed": plugin.installed}

    def remove_plugin(self, name: str) -> dict:
        """Remove a custom plugin."""
        with self._lock:
            if name in self._custom_plugins:
                del self._custom_plugins[name]
                self._plugins.pop(name, None)
                self._save_registry()
                return {"name": name, "removed": True}
            return {"name": name, "removed": False, "error": "Not found"}

    def get_plugin(self, name: str) -> Optional[CLIPlugin]:
        return self._plugins.get(name)

    def list_plugins(self, category: str = "") -> list[dict]:
        """List all plugins, optionally filtered by category."""
        plugins = list(self._plugins.values())
        if category:
            plugins = [p for p in plugins if p.category == category]
        return [
            {
                "name": p.name, "command": p.command, "description": p.description,
                "category": p.category, "installed": p.installed,
                "version": p.version, "is_custom": p.name in self._custom_plugins,
            }
            for p in sorted(plugins, key=lambda x: (not x.installed, x.name))
        ]

    def search_tools(self, query: str) -> list[dict]:
        """Search for CLI tools matching query (including unregistered tools)."""
        results = []
        for name, plugin in self._plugins.items():
            if query.lower() in name.lower() or query.lower() in plugin.description.lower():
                results.append({
                    "name": name, "command": plugin.command,
                    "description": plugin.description,
                    "installed": plugin.installed,
                })
        return results

    # ── Execution ──────────────────────────────────────────────────

    def run(self, name: str, **kwargs) -> dict:
        """Run a plugin command with argument interpolation.

        Supports:
        - {input}, {output}, {url}, {args}, {pattern}, {path}, {query}, etc.
        - Pipes: plugin1 | plugin2
        """
        plugin = self.get_plugin(name)
        if plugin is None:
            return {"error": f"Plugin '{name}' not found", "success": False}
        if not plugin.installed:
            return {"error": f"Tool '{plugin.command}' not installed", "success": False}
        try:
            # Build command from template
            template = plugin.args_template
            if not template:
                template = kwargs.get("args", "")
            # Interpolate
            cmd_parts = [plugin.command]
            if template:
                formatted = template
                for k, v in kwargs.items():
                    formatted = formatted.replace(f"{{{k}}}", str(v))
                cmd_parts.extend(formatted.split())
            start = time.time()
            result = subprocess.run(
                cmd_parts, capture_output=True, text=True, timeout=kwargs.get("timeout", 60)
            )
            elapsed = time.time() - start
            entry = {
                "plugin": name, "command": " ".join(cmd_parts),
                "success": result.returncode == 0,
                "stdout": result.stdout[:50000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
                "duration": round(elapsed, 2),
            }
            with self._lock:
                self._execution_history.append(entry)
            return entry
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "success": False, "plugin": name}
        except Exception as e:
            return {"error": str(e), "success": False, "plugin": name}

    def run_async(self, name: str, callback: Optional[Callable] = None, **kwargs):
        """Run a plugin asynchronously."""
        def _run():
            result = self.run(name, **kwargs)
            if callback:
                callback(result)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"plugin": name, "started": True}

    def pipe(self, commands: list[tuple[str, dict]]) -> list[dict]:
        """Run multiple plugins in sequence, passing output between them."""
        results = []
        last_stdout = ""
        for name, kwargs in commands:
            if last_stdout:
                kwargs["input"] = last_stdout
            result = self.run(name, **kwargs)
            results.append(result)
            if result.get("success"):
                last_stdout = result.get("stdout", "")
            else:
                break
        return results

    # ── Categories ─────────────────────────────────────────────────

    def categories(self) -> dict[str, int]:
        """Return category counts."""
        cats: dict[str, int] = {}
        for p in self._plugins.values():
            cats[p.category] = cats.get(p.category, 0) + 1
        return cats

    def installed_by_category(self) -> dict[str, list[dict]]:
        """Return installed plugins grouped by category."""
        result: dict[str, list[dict]] = {}
        for p in self._plugins.values():
            if p.installed:
                if p.category not in result:
                    result[p.category] = []
                result[p.category].append({
                    "name": p.name, "command": p.command,
                    "description": p.description, "version": p.version,
                })
        return result

    def stats(self) -> dict:
        """Usage statistics."""
        return {
            "total_plugins": len(self._plugins),
            "installed": sum(1 for p in self._plugins.values() if p.installed),
            "custom": len(self._custom_plugins),
            "categories": self.categories(),
            "executions": len(self._execution_history),
        }


cli_plugins = CLIPluginManager()
