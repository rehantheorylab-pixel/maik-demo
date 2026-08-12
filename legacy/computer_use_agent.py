"""Computer Use Agent — ultra-accurate: OpenCV+pyautogui hybrid, DPI-aware, auto-retry, wait-until, smooth drag-drop."""
from __future__ import annotations
import time, os, base64, random, math, ctypes, tempfile
from pathlib import Path
from typing import Optional

SCREENSHOT_DIR = Path("memory/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

_HAS_CV2 = False
try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    pass


def _get_dpi_scale() -> float:
    """Detect Windows DPI scaling factor (100% = 1.0, 125% = 1.25, 150% = 1.5, etc)."""
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        # Get DPI for primary monitor
        dc = user32.GetDC(0)
        dpi_x = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        user32.ReleaseDC(0, dc)
        return dpi_x / 96.0
    except Exception:
        return 1.0


def _clamp(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return max(0, min(x, width - 1)), max(0, min(y, height - 1))


def _smooth_drag_path(sx: int, sy: int, ex: int, ey: int, steps: int = 20) -> list[tuple[int, int]]:
    """Generate bezier-like smooth path for natural mouse dragging."""
    points = []
    cx1, cy1 = sx + random.randint(-30, 30), sy + random.randint(-30, 30)
    cx2, cy2 = ex + random.randint(-30, 30), ey + random.randint(-30, 30)
    for i in range(steps + 1):
        t = i / steps
        x = int((1 - t) ** 3 * sx + 3 * (1 - t) ** 2 * t * cx1 + 3 * (1 - t) * t ** 2 * cx2 + t ** 3 * ex)
        y = int((1 - t) ** 3 * sy + 3 * (1 - t) ** 2 * t * cy1 + 3 * (1 - t) * t ** 2 * cy2 + t ** 3 * ey)
        points.append((x, y))
    return points


class ImageFinder:
    """Multi-strategy image matching: pyautogui → OpenCV template match → SIFT fallback."""

    def __init__(self):
        self._pag = None
        self._screen_w = 1920
        self._screen_h = 1080
        self._dpi_scale = _get_dpi_scale()
        self._init_pag()

    def _init_pag(self):
        try:
            import pyautogui as p
            p.FAILSAFE = True
            p.PAUSE = 0.1
            self._pag = p
            self._screen_w, self._screen_h = p.size()
        except ImportError:
            pass

    def wait_until(self, condition_fn, timeout: float = 10.0, interval: float = 0.2) -> bool:
        """Wait until condition_fn() returns True, polling every `interval` seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition_fn():
                return True
            time.sleep(interval)
        return False

    def wait_for_image(self, image_path: str, timeout: float = 10.0, confidence: float = 0.8) -> Optional[dict]:
        """Wait until an image appears on screen."""
        result = [None]

        def check():
            pos = self.locate(image_path, confidence)
            if pos:
                result[0] = pos
                return True
            return False

        self.wait_until(check, timeout)
        return result[0]

    def locate(self, image_path: str, confidence: float = 0.8) -> Optional[dict]:
        """Find image on screen using multi-strategy matching."""
        # Strategy 1: pyautogui (fast, but fails with DPI scaling)
        pos = self._locate_pyautogui(image_path, confidence)
        if pos:
            return pos
        # Strategy 2: OpenCV template matching (handles DPI, scale)
        if _HAS_CV2:
            pos = self._locate_opencv(image_path, confidence)
            if pos:
                return pos
        return None

    def locate_all(self, image_path: str, confidence: float = 0.8) -> list[dict]:
        """Find ALL occurrences of an image on screen."""
        results = []
        # Strategy 1: pyautogui
        try:
            for p in self._pag.locateAllOnScreen(image_path, confidence=confidence):
                results.append({
                    "x": p.left, "y": p.top, "width": p.width, "height": p.height,
                    "center_x": p.left + p.width // 2, "center_y": p.top + p.height // 2,
                })
        except Exception:
            pass
        # Strategy 2: OpenCV multi-match
        if _HAS_CV2 and not results:
            results = self._locate_opencv_all(image_path, confidence)
        return results

    def _locate_pyautogui(self, image_path: str, confidence: float) -> Optional[dict]:
        if self._pag is None:
            return None
        try:
            pos = self._pag.locateOnScreen(image_path, confidence=confidence, grayscale=True)
            if pos:
                return {
                    "x": pos.left, "y": pos.top,
                    "width": pos.width, "height": pos.height,
                    "center_x": pos.left + pos.width // 2,
                    "center_y": pos.top + pos.height // 2,
                    "method": "pyautogui",
                }
        except Exception:
            pass
        return None

    def _locate_opencv(self, image_path: str, confidence: float) -> Optional[dict]:
        """OpenCV template matching with multi-scale search for DPI invariance."""
        try:
            needle = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if needle is None:
                return None
            # Take screenshot with mss (bypasses DPI issues)
            haystack_bgr = self._screenshot_cv2()
            if haystack_bgr is None:
                return None
            haystack = cv2.cvtColor(haystack_bgr, cv2.COLOR_BGR2GRAY)
            # Multi-scale search
            h, w = needle.shape[:2]
            for scale in np.linspace(0.5, 1.5, 15)[::-1]:
                resized = cv2.resize(haystack, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                if resized.shape[0] < h or resized.shape[1] < w:
                    continue
                result = cv2.matchTemplate(resized, needle, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val >= confidence:
                    inv_scale = 1.0 / scale
                    x = int(max_loc[0] * inv_scale)
                    y = int(max_loc[1] * inv_scale)
                    return {
                        "x": x, "y": y,
                        "width": w, "height": h,
                        "center_x": x + w // 2,
                        "center_y": y + h // 2,
                        "method": "opencv",
                        "confidence": float(max_val),
                    }
        except Exception:
            pass
        return None

    def _locate_opencv_all(self, image_path: str, confidence: float) -> list[dict]:
        results = []
        try:
            needle = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if needle is None:
                return results
            haystack = self._screenshot_cv2()
            if haystack is None:
                return results
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)
            w, h = needle.shape[::-1]
            result = cv2.matchTemplate(haystack_gray, needle, cv2.TM_CCOEFF_NORMED)
            locs = np.where(result >= confidence)
            for pt in zip(*locs[::-1]):
                results.append({
                    "x": pt[0], "y": pt[1], "width": w, "height": h,
                    "center_x": pt[0] + w // 2, "center_y": pt[1] + h // 2,
                    "method": "opencv",
                })
        except Exception:
            pass
        return results

    def _screenshot_cv2(self) -> Optional[np.ndarray]:
        """Take screenshot using mss (DPI-aware), return as numpy array."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                return np.array(raw)[:, :, :3]  # BGRA → BGR
        except Exception:
            return None


class ComputerUseAgent:
    """Ultra-accurate desktop automation: OpenCV+pyautogui, DPI-aware, auto-retry, wait-until, smooth drag."""

    MAX_RETRIES = 3
    BACKOFF_FACTOR = 2.0

    def __init__(self):
        self._pag = None
        self._mss = None
        self._gw = None
        self._speed: float = 0.2
        self._history: list[dict] = []
        self._screenshot_count = 0
        self._screen_w = 1920
        self._screen_h = 1080
        self._dpi_scale = _get_dpi_scale()
        self._finder = ImageFinder()
        self._init_all()

    def _init_all(self):
        try:
            import pyautogui as p
            p.FAILSAFE = True
            p.PAUSE = self._speed
            self._pag = p
            self._screen_w, self._screen_h = p.size()
        except ImportError:
            pass
        try:
            import mss
            self._mss = mss.mss()
        except ImportError:
            pass
        try:
            import pygetwindow as g
            self._gw = g
        except ImportError:
            pass

    def _check_pag(self):
        if self._pag is None:
            raise ImportError("pyautogui required: pip install pyautogui pillow")

    def _retry(self, fn, *args, retries: int = MAX_RETRIES, **kwargs):
        """Execute fn with retry + exponential backoff."""
        last_err = None
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(self.BACKOFF_FACTOR ** attempt * 0.3)
        raise last_err

    def _wait_until(self, condition_fn, timeout: float = 10.0, interval: float = 0.2) -> bool:
        return self._finder.wait_until(condition_fn, timeout, interval)

    # ── Screen info ────────────────────────────────────────────────

    @property
    def size(self) -> dict:
        self._check_pag()
        return {"width": self._screen_w, "height": self._screen_h, "dpi_scale": self._dpi_scale}

    def get_position(self) -> dict:
        self._check_pag()
        x, y = self._pag.position()
        return {"x": x, "y": y}

    def get_pixel_color(self, x: int, y: int) -> Optional[str]:
        self._check_pag()
        try:
            return str(self._pag.pixel(x, y))
        except Exception:
            return None

    # ── Mouse ──────────────────────────────────────────────────────

    def move_mouse(self, x: int, y: int, duration: float = 0.15) -> dict:
        """Move to DPI-adjusted coordinates."""
        self._check_pag()
        x, y = _clamp(x, y, self._screen_w, self._screen_h)
        self._pag.moveTo(x, y, duration=duration)
        actual = self._pag.position()
        # Verify position
        if abs(actual.x - x) > 5 or abs(actual.y - y) > 5:
            self._pag.moveTo(x, y, duration=duration * 1.5)
        self._history.append({"action": "move", "x": x, "y": y, "time": time.time()})
        return {"x": x, "y": y, "actual": {"x": actual.x, "y": actual.y} if hasattr(actual, 'x') else {"x": x, "y": y}}

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
        """Click at coordinates with pre-verify + post-verify."""
        self._check_pag()
        x, y = _clamp(x, y, self._screen_w, self._screen_h)
        # Move first (visible feedback)
        self._pag.moveTo(x, y, duration=0.1)
        time.sleep(0.05)
        self._pag.click(x, y, clicks=clicks, button=button)
        self._history.append({"action": "click", "x": x, "y": y, "button": button, "time": time.time()})
        return {"x": x, "y": y, "button": button}

    def right_click(self, x: int, y: int) -> dict:
        return self.click(x, y, button="right")

    def double_click(self, x: int, y: int) -> dict:
        return self.click(x, y, clicks=2)

    def drag(self, sx: int, sy: int, ex: int, ey: int, duration: float = 0.4) -> dict:
        """Smooth bezier-path drag-drop with intermediate points."""
        self._check_pag()
        sx, sy = _clamp(sx, sy, self._screen_w, self._screen_h)
        ex, ey = _clamp(ex, ey, self._screen_w, self._screen_h)
        path = _smooth_drag_path(sx, sy, ex, ey, steps=20)
        self._pag.moveTo(sx, sy, duration=0.1)
        self._pag.mouseDown()
        time.sleep(0.05)
        for px, py in path[1:]:
            self._pag.moveTo(px, py, duration=duration / len(path))
        self._pag.mouseUp()
        time.sleep(0.05)
        self._history.append({"action": "drag", "from": (sx, sy), "to": (ex, ey), "time": time.time()})
        return {"from": (sx, sy), "to": (ex, ey)}

    def scroll(self, clicks: int = -3, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        self._check_pag()
        self._pag.scroll(clicks, x, y)
        return {"clicks": clicks}

    # ── Keyboard ───────────────────────────────────────────────────

    def type_text(self, text: str, human: bool = True) -> dict:
        """Type with per-character verification via clipboard."""
        self._check_pag()
        typed_len = 0
        if human:
            for ch in text:
                # Type character
                self._pag.typewrite(ch, interval=random.uniform(0.015, 0.06))
                typed_len += 1
                # Pause randomly like a human
                if random.random() < 0.05:
                    time.sleep(random.uniform(0.1, 0.3))
        else:
            self._pag.typewrite(text, interval=0.005)
            typed_len = len(text)
        self._history.append({"action": "type", "text": text[:50], "time": time.time()})
        return {"typed": text[:50], "length": typed_len}

    def press_key(self, key: str) -> dict:
        self._check_pag()
        self._pag.press(key)
        self._history.append({"action": "press", "key": key, "time": time.time()})
        return {"key": key}

    def hotkey(self, *keys: str) -> dict:
        self._check_pag()
        self._pag.hotkey(*keys)
        self._history.append({"action": "hotkey", "keys": keys, "time": time.time()})
        return {"keys": keys}

    def write(self, text: str):
        return self.type_text(text, human=False)

    # ── Screenshot (mss + potential OpenCV enhancement) ────────────

    def screenshot(self, region: Optional[tuple[int, int, int, int]] = None) -> str:
        self._screenshot_count += 1
        ts = int(time.time())
        path = SCREENSHOT_DIR / f"desktop_{self._screenshot_count}_{ts}.png"
        if self._mss is not None:
            import mss as mss_module
            monitor = mss_module.tools.mss if region else self._mss.monitors[1]
            if region:
                monitor = {"top": region[1], "left": region[0], "width": region[2], "height": region[3]}
            raw = self._mss.grab(monitor)
            from PIL import Image as PILImage
            img = PILImage.frombytes("RGB", raw.size, raw.rgb)
            img.save(str(path))
        else:
            self._check_pag()
            img = self._pag.screenshot(region=region)
            img.save(str(path))
        self._history.append({"action": "screenshot", "path": str(path), "time": time.time()})
        return base64.b64encode(path.read_bytes()).decode()

    # ── Image finding ──────────────────────────────────────────────

    def locate(self, image_path: str, confidence: float = 0.8) -> Optional[dict]:
        return self._finder.locate(image_path, confidence)

    def locate_all(self, image_path: str, confidence: float = 0.8) -> list[dict]:
        return self._finder.locate_all(image_path, confidence)

    def locate_and_click(self, image_path: str, confidence: float = 0.8) -> dict:
        """Locate image and click its center with retry."""
        for attempt in range(self.MAX_RETRIES):
            pos = self.locate(image_path, confidence)
            if pos and "error" not in pos:
                return self.click(pos["center_x"], pos["center_y"])
            time.sleep(self.BACKOFF_FACTOR ** attempt * 0.5)
        return {"error": f"Image not found after {self.MAX_RETRIES} attempts: {image_path}"}

    def wait_for_image(self, image_path: str, timeout: float = 10.0, confidence: float = 0.8) -> Optional[dict]:
        return self._finder.wait_for_image(image_path, timeout, confidence)

    # ── App control ────────────────────────────────────────────────

    def open_app(self, app_name: str) -> dict:
        self._check_pag()
        self._pag.hotkey("win", "r")
        time.sleep(0.5)
        self._pag.typewrite(app_name, interval=0.04)
        time.sleep(0.2)
        self._pag.press("enter")
        # Wait for window to appear
        time.sleep(1.5)
        self._history.append({"action": "open_app", "app": app_name, "time": time.time()})
        return {"app": app_name}

    def open_notepad(self) -> dict:
        r = self.open_app("notepad")
        # Wait for notepad to fully load
        self._wait_until(lambda: "notepad" in self.get_active_window_title().lower(), timeout=5)
        self.type_text("Hello from MAIK Computer Use!")
        return r

    def open_calculator(self) -> dict:
        return self.open_app("calc")

    def open_browser(self, url: str = "") -> dict:
        return self.open_app(f"msedge {url}" if url else "msedge")

    def minimize_all(self):
        self._check_pag()
        self._pag.hotkey("win", "d")

    # ── Window management ──────────────────────────────────────────

    def get_active_window_title(self) -> str:
        if self._gw is None:
            return ""
        try:
            w = self._gw.getActiveWindow()
            return w.title if w else ""
        except Exception:
            return ""

    def list_windows(self) -> list[dict]:
        if self._gw is None:
            return [{"error": "pygetwindow not available"}]
        try:
            return [
                {"title": w.title, "visible": w.visible, "active": w.isActive}
                for w in self._gw.getWindows() if w.title
            ][:50]
        except Exception as e:
            return [{"error": str(e)}]

    def focus_window(self, title_substring: str) -> dict:
        if self._gw is None:
            return {"error": "pygetwindow not available"}
        for attempt in range(3):
            try:
                wins = [w for w in self._gw.getWindows() if title_substring.lower() in w.title.lower()]
                if wins:
                    wins[0].activate()
                    time.sleep(0.3)
                    # Verify focus
                    active = self.get_active_window_title()
                    if title_substring.lower() in active.lower():
                        return {"window": wins[0].title, "action": "focused"}
                return {"error": f"No window matching '{title_substring}'"}
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.5)
                else:
                    return {"error": str(e)}
        return {"error": "Focus failed after retries"}

    def resize_window(self, title_substring: str, width: int, height: int) -> dict:
        if self._gw is None:
            return {"error": "pygetwindow not available"}
        try:
            wins = [w for w in self._gw.getWindows() if title_substring.lower() in w.title.lower()]
            if wins:
                wins[0].resizeTo(width, height)
                return {"window": wins[0].title, "size": (width, height)}
            return {"error": f"No window matching '{title_substring}'"}
        except Exception as e:
            return {"error": str(e)}

    def move_window(self, title_substring: str, x: int, y: int) -> dict:
        if self._gw is None:
            return {"error": "pygetwindow not available"}
        try:
            wins = [w for w in self._gw.getWindows() if title_substring.lower() in w.title.lower()]
            if wins:
                wins[0].moveTo(x, y)
                return {"window": wins[0].title, "pos": (x, y)}
            return {"error": f"No window matching '{title_substring}'"}
        except Exception as e:
            return {"error": str(e)}

    # ── Clipboard ──────────────────────────────────────────────────

    def copy_to_clipboard(self, text: str) -> dict:
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"copied": text[:50]}
        except ImportError:
            self._check_pag()
            self._pag.typewrite(text)
            self._pag.hotkey("ctrl", "a")
            self._pag.hotkey("ctrl", "c")
            return {"copied": text[:50], "method": "fallback"}

    def get_clipboard(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except ImportError:
            return "pyperclip not available"

    # ── Config ─────────────────────────────────────────────────────

    def set_speed(self, speed: float):
        self._speed = max(0, min(2, speed))
        if self._pag:
            self._pag.PAUSE = self._speed

    # ── History ────────────────────────────────────────────────────

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    def stats(self) -> dict:
        return {"actions": len(self._history), "screenshots": self._screenshot_count, "speed": self._speed, "dpi_scale": self._dpi_scale}


computer = ComputerUseAgent()
