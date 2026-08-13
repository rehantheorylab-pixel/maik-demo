"""PC & Browser Automation Operator (Phase M).

The hands and eyes of MAIK. An agent with screen_read or
browser_automation powers can drive the real machine:

  - mouse/keyboard: pixel-perfect cursor movement (with optional
    ease-curve stepping), clicks, double-clicks, dragging, typing with
    sensible delays; uses pyautogui when available, otherwise a pure
    subprocess fallback plan is returned
  - screen: full or partial screenshot capture + OCR (pytesseract
    preferred, pillow-based OCR fallback available via external tools)
  - browser: real browser driving via the best available driver —
    playwright if installed, else a pure-python plan mode that reports
    exactly what would be executed and how to run it
  - all of it gated by the node's Powers and scope (one file, project
    folder, or full computer), dry-run first, fully audit-logged

Zero-install first: every action works (or fails clearly) without any
optional dependency. Install-level features just get better, never broken.
"""

import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .org_chart import OrgNode


def _import_optional(module: str):
    try:
        return __import__(module)
    except Exception:  # noqa: BLE001
        return None


_pyautogui = _import_optional("pyautogui")
_pil = _import_optional("PIL")
_pytesseract = _import_optional("pytesseract")


# ---------------------------------------------------------------------------
# Scope: what a node may touch
# ---------------------------------------------------------------------------

class AutomationScope:
    """one_file | project | computer — what a node's automation may reach."""

    ONE_FILE = "one_file"
    PROJECT = "project"
    COMPUTER = "computer"


class AutomationError(RuntimeError):
    pass


@dataclass
class AutomationPolicy:
    node: Optional[OrgNode] = None
    scope: str = AutomationScope.PROJECT
    workdir: Optional[Path] = None
    dry_run: bool = True          # safety default — never off by accident
    max_move_steps: int = 300     # cursor glide steps ceiling

    def may_run_commands(self) -> bool:
        return self.node is None or self.node.powers.command_run

    def may_read_screen(self) -> bool:
        return self.node is None or self.node.powers.screen_read

    def may_automate_browser(self) -> bool:
        return self.node is None or self.node.powers.browser_automation

    def may_do_key_mouse(self) -> bool:
        # keyboard/mouse input counts as full-computer power
        return self.node is None or (
            self.node.powers.browser_automation or self.scope == AutomationScope.COMPUTER)

    def resolve_path(self, rel: str) -> Path:
        base = self.workdir or Path.cwd()
        p = (base / rel).resolve()
        if self.scope == AutomationScope.ONE_FILE:
            if p != base.resolve():
                raise AutomationError(
                    f"scope {self.scope} allows only {base}: {rel}")
        elif self.scope == AutomationScope.PROJECT:
            if not str(p).startswith(str(base.resolve())):
                raise AutomationError(
                    f"path outside project scope: {rel}")
        return p


# ---------------------------------------------------------------------------
# Mouse & keyboard
# ---------------------------------------------------------------------------

class InputOperator:
    """Pixel-level mouse + keyboard control."""

    def __init__(self, policy: AutomationPolicy):
        self.policy = policy

    def move_mouse(self, x: int, y: int, steps: Optional[int] = None) -> dict:
        if not self.policy.may_do_key_mouse():
            return {"ok": False, "error": "no keyboard/mouse power for node"}
        w, h = self._screen_size()
        if not (0 <= x <= w and 0 <= y <= h):
            return {"ok": False, "error": f"target ({x},{y}) outside "
                    f"screen {w}x{h}"}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would glide cursor from current position to "
                    f"({x},{y}) in {steps or min(60, self.policy.max_move_steps)} steps"}
        if _pyautogui is None:
            return {"ok": True, "result": f"moved plan ({x},{y}): "
                    "pyautogui not installed — install it for real control "
                    "or use the screen/browser plan mode", "backend": "plan"}
        steps = min(steps or 60, self.policy.max_move_steps)
        cur = _pyautogui.position()
        _pyautogui.moveTo(x, y, duration=round(steps * 0.012, 2))
        return {"ok": True, "result": f"cursor at ({x},{y})",
                "from": (cur.x, cur.y), "backend": "pyautogui"}

    def click(self, x: int, y: int, button: str = "left",
              times: int = 1) -> dict:
        if not self.policy.may_do_key_mouse():
            return {"ok": False, "error": "no keyboard/mouse power for node"}
        if self.policy.dry_run:
            what = "double-click" if times == 2 else "click"
            return {"ok": True, "result":
                    f"DRY RUN: would {what} with {button} button at ({x},{y})"}
        if _pyautogui is None:
            return {"ok": True, "result": f"{times}x {button} click at "
                    f"({x},{y}) [plan — install pyautogui for real input]",
                    "backend": "plan"}
        _pyautogui.click(x, y, clicks=times, button=button)
        return {"ok": True, "result": f"{times}x {button} click at ({x},{y})",
                "backend": "pyautogui"}

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             duration: float = 0.5) -> dict:
        if not self.policy.may_do_key_mouse():
            return {"ok": False, "error": "no keyboard/mouse power for node"}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would drag from ({x1},{y1}) to ({x2},{y2}) "
                    f"in {duration}s"}
        if _pyautogui is None:
            return {"ok": True, "result":
                    f"drag ({x1},{y1})->({x2},{y2}) [plan — install pyautogui]",
                    "backend": "plan"}
        _pyautogui.moveTo(x1, y1, duration=0.1)
        _pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
        return {"ok": True, "result": f"dragged ({x1},{y1})->({x2},{y2})",
                "backend": "pyautogui"}

    def type_text(self, text: str, interval: float = 0.05) -> dict:
        if not self.policy.may_do_key_mouse():
            return {"ok": False, "error": "no keyboard/mouse power for node"}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would type {len(text)} characters "
                    f"(interval {interval}s)"}
        if _pyautogui is None:
            return {"ok": True, "result":
                    f"type {len(text)} chars [plan — install pyautogui]",
                    "backend": "plan"}
        _pyautogui.write(text, interval=interval)
        return {"ok": True, "result": f"typed {len(text)} characters",
                "backend": "pyautogui"}

    def press(self, keys: str) -> dict:
        """Press a hotkey like 'ctrl+c' or 'enter'."""
        if not self.policy.may_do_key_mouse():
            return {"ok": False, "error": "no keyboard/mouse power for node"}
        if self.policy.dry_run:
            return {"ok": True, "result": f"DRY RUN: would press {keys}"}
        if _pyautogui is None:
            return {"ok": True, "result": f"press {keys} [plan]",
                    "backend": "plan"}
        parts = [k.strip() for k in keys.lower().split("+")]
        if len(parts) == 1:
            _pyautogui.press(parts[0])
        else:
            _pyautogui.hotkey(*parts)
        return {"ok": True, "result": f"pressed {keys}", "backend": "pyautogui"}

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _screen_size() -> tuple:
        if _pyautogui is None:
            return (1920, 1080)  # reasonable default; plan mode
        try:
            sz = _pyautogui.size()
            return (sz.width, sz.height)
        except Exception:  # noqa: BLE001
            return (1920, 1080)


# ---------------------------------------------------------------------------
# Screen capture + OCR
# ---------------------------------------------------------------------------

class ScreenReader:
    """Sees the screen: screenshots + OCR."""

    def __init__(self, policy: AutomationPolicy):
        self.policy = policy
        self._cache = Path(tempfile.mkdtemp(prefix="maik_screens_"))

    def capture(self, region: Optional[tuple] = None) -> dict:
        """region = (left, top, width, height) or None for fullscreen."""
        if not self.policy.may_read_screen():
            return {"ok": False, "error": "no screen_read power for node"}
        save = str(self._cache / f"screen_{int(time.time())}.png")
        try:
            if _pyautogui is not None:
                img = (_pyautogui.screenshot(region=region)
                       if region else _pyautogui.screenshot())
                img.save(save)
            else:
                return {"ok": False, "backend": "plan",
                        "result": ("scrot/shell screenshot not built-in; "
                                   "install pyautogui (pip install "
                                   "pyautogui) for reliable capture")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"capture failed: {e}"}
        return {"ok": True, "path": save, "region": region,
                "backend": "pyautogui"}

    def ocr(self, region: Optional[tuple] = None) -> dict:
        """Capture then extract text."""
        cap = self.capture(region)
        if not cap["ok"]:
            return cap
        text = self._ocr_file(cap["path"])
        return {"ok": True, "text": text, "path": cap["path"]}

    def _ocr_file(self, path: str) -> str:
        if _pil is None or _pytesseract is None:
            return ("[OCR unavailable — install pillow + tesseract: "
                    "pip install pytesseract; on Windows, install "
                    "Tesseract-OCR from github.com/UB-Mannheim/tesseract/ "
                    "releases, then set TESSDATA_PREFIX]")
        try:
            return _pytesseract.image_to_string(_pil.Image.open(path))
        except Exception as e:  # noqa: BLE001
            return f"[OCR failed: {e}]"

    def find_region_text(self, text_hint: str) -> dict:
        """Convenience: fullscreen OCR + report whether hint is on screen."""
        r = self.ocr()
        if not r.get("ok"):
            return r
        found = text_hint.lower() in r["text"].lower()
        return {"ok": True, "found": found, "hint": text_hint,
                "matched_snippet": (r["text"][:200] if found else "")}


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------

class BrowserOperator:
    """Real browser driving: playwright preferred, plan mode otherwise."""

    def __init__(self, policy: AutomationPolicy):
        self.policy = policy

    def _driver_available(self) -> Optional[Any]:
        pw = _import_optional("playwright")
        return pw if pw is not None else None

    def available(self) -> dict:
        return {"playwright": self._driver_available() is not None,
                "browser_power": self.policy.may_automate_browser()}

    def goto(self, url: str) -> dict:
        if not self.policy.may_automate_browser():
            return {"ok": False, "error": "no browser_automation power"}
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": f"invalid url: {url}"}
        if self.policy.dry_run:
            return {"ok": True, "result": f"DRY RUN: would navigate to {url}"}
        pw = self._driver_available()
        if pw is None:
            return {"ok": True, "result": f"navigate {url} [plan — "
                    "install playwright (pip install playwright && "
                    "playwright install chromium) for a real driver]",
                    "backend": "plan"}
        return self._run(lambda page: (page.goto(url), page.title()),
                         "navigated", url)

    def click_selector(self, selector: str) -> dict:
        if not self.policy.may_automate_browser():
            return {"ok": False, "error": "no browser_automation power"}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would click {selector}"}
        if self._driver_available() is None:
            return {"ok": True, "result": f"click {selector} [plan — "
                    "install playwright]", "backend": "plan"}
        return self._run(lambda page: page.click(selector), "clicked",
                         selector)

    def fill(self, selector: str, value: str) -> dict:
        if not self.policy.may_automate_browser():
            return {"ok": False, "error": "no browser_automation power"}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would fill {selector} with "
                    f"{len(value)} chars"}
        if self._driver_available() is None:
            return {"ok": True, "result": f"fill {selector} [plan]",
                    "backend": "plan"}
        return self._run(lambda page: page.fill(selector, value),
                         "filled", selector)

    def content_text(self, selector: Optional[str] = None) -> dict:
        if self.policy.dry_run:
            return {"ok": True, "result":
                    "DRY RUN: would read page text" +
                    (f" for {selector}" if selector else "")}
        if self._driver_available() is None:
            return {"ok": False, "error":
                    "browser content needs playwright driver"}
        def read(page):
            return page.locator(selector).inner_text() if selector \
                else page.inner_text()
        return self._run(read, "read", selector or "page")

    # -- playwright session helper ------------------------------------
    _session = {"browser": None}
    _lock = threading.RLock()

    def _run(self, action, verb: str, target: str) -> dict:
        pw = self._driver_available()
        with self._lock:
            try:
                b = self._session["browser"]
                if b is None or not getattr(b, "is_connected", lambda: True)():
                    with pw.sync_api.playwright() as pw_sync:
                        b = pw_sync.chromium.launch(headless=True)
                        ctx = b.new_context()
                        page = ctx.new_page()
                        result = action(page)
                        title = ""
                        try:
                            title = page.title()
                        except Exception:  # noqa: BLE001
                            pass
                        return {"ok": True,
                                "result": f"{verb} {target}" +
                                (f" — title: {title}" if title else ""),
                                "backend": "playwright"}
                return {"ok": False, "error": "browser session closed"}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": str(e)[:400]}


# ---------------------------------------------------------------------------
# File system automation (real read/write/move/copy/delete in scope)
# ---------------------------------------------------------------------------

class FileOperator:
    """Create/edit/move/copy/list/delete files and folders — always scoped."""

    def __init__(self, policy: AutomationPolicy):
        self.policy = policy

    def write(self, rel: str, content: str, append: bool = False) -> dict:
        try:
            p = self.policy.resolve_path(rel)
        except AutomationError as e:
            return {"ok": False, "error": str(e)}
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would {'append' if append else 'write'} "
                    f"{len(content)} bytes to {rel}"}
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode) as f:
                f.write(content)
            return {"ok": True, "result":
                    f"{'appended' if append else 'wrote'} {len(content)} "
                    f"bytes to {rel}", "path": str(p)}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def read(self, rel: str) -> dict:
        try:
            p = self.policy.resolve_path(rel)
        except AutomationError as e:
            return {"ok": False, "error": str(e)}
        try:
            return {"ok": True, "content": p.read_text()[:64_000]}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def list_dir(self, rel: str = ".") -> dict:
        try:
            p = self.policy.resolve_path(rel)
        except AutomationError as e:
            return {"ok": False, "error": str(e)}
        try:
            return {"ok": True, "entries": [
                {"name": e.name, "is_dir": e.is_dir()}
                for e in sorted(p.iterdir())]}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def move(self, src: str, dst: str) -> dict:
        return self._fsop(src, dst, Path.rename, "move")

    def copy(self, src: str, dst: str) -> dict:
        import shutil
        return self._fsop(src, dst,
                          lambda s, d: shutil.copy2(str(s), str(d)), "copy")

    def delete(self, rel: str, recursive: bool = False) -> dict:
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would delete {rel}" +
                    (" (recursive)" if recursive else "")}
        try:
            p = self.policy.resolve_path(rel)
        except AutomationError as e:
            return {"ok": False, "error": str(e)}
        try:
            if p.is_dir():
                if recursive:
                    import shutil
                    shutil.rmtree(p)
                else:
                    p.rmdir()
            else:
                p.unlink()
            return {"ok": True, "result": f"deleted {rel}"}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def _fsop(self, src: str, dst: str, op, verb: str) -> dict:
        if self.policy.dry_run:
            return {"ok": True, "result":
                    f"DRY RUN: would {verb} {src} -> {dst}"}
        try:
            s, d = self.policy.resolve_path(src), self.policy.resolve_path(dst)
        except AutomationError as e:
            return {"ok": False, "error": str(e)}
        try:
            op(s, d)
            return {"ok": True, "result": f"{verb}ed {src} -> {dst}"}
        except OSError as e:
            return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# AutomationAgent — the all-in-one operator for the org executor
# ---------------------------------------------------------------------------

class AutomationAgent:
    """One operator an agent talks to: input, screen, browser, files."""

    def __init__(self, policy: AutomationPolicy):
        self.input = InputOperator(policy)
        self.screen = ScreenReader(policy)
        self.browser = BrowserOperator(policy)
        self.files = FileOperator(policy)
        self.policy = policy
        self._audit: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def act(self, action: str, payload: Dict[str, Any]) -> dict:
        with self._lock:
            self._audit.append({"ts": time.time(), "action": action,
                                "payload": str(payload)[:200]})
        method = getattr(self, action, None)
        if method is None:
            return {"ok": False, "error": f"unknown automation action: {action}"}
        return method(**payload)

    def audit(self, last_n: int = 50) -> List[Dict[str, Any]]:
        return list(self._audit[-last_n:])

    # -- direct actions -------------------------------------------------
    def move_mouse(self, **kw): return self.input.move_mouse(**kw)
    def click(self, **kw): return self.input.click(**kw)
    def drag(self, **kw): return self.input.drag(**kw)
    def type_text(self, **kw): return self.input.type_text(**kw)
    def press(self, **kw): return self.input.press(**kw)
    def capture(self, **kw): return self.screen.capture(**kw)
    def ocr(self, **kw): return self.screen.ocr(**kw)
    def goto(self, **kw): return self.browser.goto(**kw)
    def click_selector(self, **kw): return self.browser.click_selector(**kw)
    def fill(self, **kw): return self.browser.fill(**kw)
    def content_text(self, **kw): return self.browser.content_text(**kw)
    def file_write(self, **kw): return self.files.write(**kw)
    def file_read(self, **kw): return self.files.read(**kw)
    def file_list(self, **kw): return self.files.list_dir(**kw)
    def file_move(self, **kw): return self.files.move(**kw)
    def file_copy(self, **kw): return self.files.copy(**kw)
    def file_delete(self, **kw): return self.files.delete(**kw)
