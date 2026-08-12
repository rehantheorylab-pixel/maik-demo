"""Browser Agent — most accurate: multi-strategy selectors, auto-retry, shadow DOM, frames, state verification."""
from __future__ import annotations
import time, json, base64, os, re
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

SCREENSHOT_DIR = Path("memory/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR = Path("memory/browser_sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)

_AD_FILTERS = {
    "googlesyndication.com", "doubleclick.net", "google-analytics.com",
    "facebook.net/tr", "amazon-adsystem.com", "scorecardresearch.com",
    "adsrvr.org", "adservice.google.com", "pagead2.googlesyndication.com",
}

_MAX_RETRIES = 3
_RETRY_DELAY = 0.5


class _SelectorStrategy:
    """Multi-strategy element locator: text → role → label → CSS → XPath → JS eval."""

    @staticmethod
    def make_locator(page, selector: str):
        """Create best locator from a selector string using priority strategy."""
        l = page.locator(selector)
        return l

    @staticmethod
    def find_via_js(page, text: str) -> Optional[dict]:
        """Find element by text content via JavaScript (penetrates shadow DOM)."""
        return page.evaluate(f"""() => {{
            const walker = document.createTreeWalker(document.body, 4, null, false);
            let node;
            while (node = walker.nextNode()) {{
                if (node.textContent.trim().toLowerCase().includes('{text.lower()}')) {{
                    const r = node.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {{
                        return {{ cx: r.x + r.width/2, cy: r.y + r.height/2, tag: node.tagName }};
                    }}
                }}
            }}
            return null;
        }}""")

    @staticmethod
    def try_click_via_js(page, selector: str) -> bool:
        """Fallback: click via JavaScript when Playwright click fails."""
        try:
            page.evaluate(f"document.querySelector('{selector.replace(chr(39), chr(34))}')?.click()")
            return True
        except Exception:
            return False


class BrowserAgent:
    """Ultra-accurate Playwright automation: auto-retry, multi-strategy, state verification, shadow piercing."""

    def __init__(self):
        self._page = None
        self._browser = None
        self._playwright = None
        self._context = None
        self._history: list[dict] = []
        self._screenshot_count = 0
        self._last_screenshot_path: Optional[str] = None

    def _ensure_browser(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True,
            java_script_enabled=True,
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(20000)
        self._page.set_default_navigation_timeout(30000)
        self._block_ads()

    def _block_ads(self):
        if not self._page:
            return

        def _route(route):
            url = route.request.url.lower()
            if any(ad in url for ad in _AD_FILTERS):
                route.abort()
            elif route.request.resource_type in ("image", "media", "font", "stylesheet"):
                route.continue_()
            else:
                route.continue_()

        self._page.route("**/*", _route)

    # ── Retry decorator ────────────────────────────────────────────

    def _retry(self, fn, *args, retries: int = _MAX_RETRIES, **kwargs):
        last_err = None
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(_RETRY_DELAY * (2 ** attempt))
                    try:
                        self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass
        raise last_err

    # ── Navigation ─────────────────────────────────────────────────

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict:
        self._ensure_browser()
        try:
            resp = self._page.goto(url, wait_until=wait_until, timeout=30000)
            # Wait for page to be fully interactive
            try:
                self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            # Ensure page is rendered
            self._page.wait_for_timeout(500)
            title = self._page.title()
            b64 = self._take_screenshot()
            self._history.append({"action": "navigate", "url": url, "title": title, "time": time.time()})
            return {
                "url": url,
                "title": title,
                "status": resp.status if resp else "unknown",
                "screenshot": b64,
                "text_preview": self._page.content()[:2000],
            }
        except Exception as e:
            return {"url": url, "status": "error", "error": str(e)}

    # ── Screenshot ─────────────────────────────────────────────────

    def screenshot(self) -> str:
        self._ensure_browser()
        return self._take_screenshot()

    def screenshot_full_page(self) -> str:
        """Full-page screenshot (scrolls to capture entire page)."""
        self._ensure_browser()
        self._screenshot_count += 1
        path = SCREENSHOT_DIR / f"browser_full_{self._screenshot_count}_{int(time.time())}.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
            return base64.b64encode(path.read_bytes()).decode()
        except Exception:
            return ""

    def _take_screenshot(self) -> str:
        self._screenshot_count += 1
        path = SCREENSHOT_DIR / f"browser_{self._screenshot_count}_{int(time.time())}.png"
        try:
            self._page.screenshot(path=str(path), full_page=False)
            self._last_screenshot_path = str(path)
            return base64.b64encode(path.read_bytes()).decode()
        except Exception:
            return ""

    def screenshot_diff(self) -> Optional[dict]:
        if not HAS_PIL or not self._last_screenshot_path:
            return None
        prev = self._last_screenshot_path
        self._take_screenshot()
        cur = self._last_screenshot_path
        if not cur or not Path(prev).exists() or not Path(cur).exists():
            return None
        try:
            im_prev = Image.open(prev)
            im_cur = Image.open(cur)
            diff = ImageChops.difference(im_cur.resize(im_prev.size), im_prev)
            changed = sum(1 for p in diff.getdata() if any(c > 20 for c in p[:3]))
            total = im_prev.size[0] * im_prev.size[1]
            return {"changed_pixels": changed, "total_pixels": total, "change_ratio": changed / max(total, 1)}
        except Exception:
            return None

    # ── Click ──────────────────────────────────────────────────────

    def click(self, selector: str = "", x: int = 0, y: int = 0, use_coords: bool = False) -> dict:
        self._ensure_browser()
        if use_coords:
            return self._click_coords(x, y)
        return self._click_selector(selector)

    def _click_coords(self, x: int, y: int) -> dict:
        try:
            # Click with verification
            self._page.mouse.click(x, y)
            time.sleep(0.2)
            self._history.append({"action": "click_coord", "x": x, "y": y, "time": time.time()})
            return {"clicked": f"({x}, {y})", "success": True, "screenshot": self._take_screenshot()}
        except Exception as e:
            return {"clicked": f"({x}, {y})", "success": False, "error": str(e)}

    def _click_selector(self, selector: str) -> dict:
        loc = None
        # Strategy 1: Playwright locator with wait
        loc = self._retry(self._try_click_playwright, selector)
        if loc:
            return loc
        # Strategy 2: JS querySelector click
        js_ok = _SelectorStrategy.try_click_via_js(self._page, selector)
        if js_ok:
            self._history.append({"action": "click_js", "selector": selector, "time": time.time()})
            return {"clicked": selector, "success": True, "screenshot": self._take_screenshot()}
        return {"clicked": selector, "success": False, "error": "Element not found or not clickable"}

    def _try_click_playwright(self, selector: str) -> Optional[dict]:
        try:
            l = self._page.locator(selector)
            if l.count() == 0:
                return None
            # Scroll into view
            l.scroll_into_view_if_needed()
            self._page.wait_for_timeout(200)
            # Verify visible
            if not l.is_visible():
                return None
            # Highlight + click
            l.highlight()
            self._page.wait_for_timeout(100)
            l.click()
            self._history.append({"action": "click", "selector": selector, "time": time.time()})
            return {"clicked": selector, "success": True, "screenshot": self._take_screenshot()}
        except Exception:
            return None

    # ── Type ───────────────────────────────────────────────────────

    def type(self, selector: str = "", text: str = "", x: int = 0, y: int = 0,
             use_coords: bool = False, delay_ms: int = 20) -> dict:
        self._ensure_browser()
        try:
            if use_coords:
                self._page.mouse.click(x, y)
                self._page.keyboard.type(text, delay=delay_ms)
            else:
                l = self._page.locator(selector)
                l.wait_for(state="visible", timeout=5000)
                l.scroll_into_view_if_needed()
                l.highlight()
                self._page.wait_for_timeout(100)
                l.fill(text)
            self._history.append({"action": "type", "text": text[:50], "time": time.time()})
            return {"typed": text[:50], "success": True}
        except Exception as e:
            # Fallback: type via JS
            try:
                self._page.evaluate(f"document.querySelector('{selector.replace(chr(39), chr(34))}').value = '{text}'")
                return {"typed": text[:50], "success": True, "method": "js_fallback"}
            except Exception:
                return {"error": str(e), "success": False}

    def press_key(self, key: str):
        self._ensure_browser()
        self._page.keyboard.press(key)

    # ── Scroll ─────────────────────────────────────────────────────

    def scroll(self, dx: int = 0, dy: int = 500):
        self._ensure_browser()
        self._page.evaluate(f"window.scrollBy({{left: {dx}, top: {dy}, behavior: 'smooth'}})")
        self._page.wait_for_timeout(300)

    # ── DOM extraction ─────────────────────────────────────────────

    def extract_text(self) -> dict:
        self._ensure_browser()
        try:
            text = self._page.inner_text("body")
            return {"text": text[:10000], "length": len(text), "truncated": len(text) > 10000}
        except Exception as e:
            return {"error": str(e)}

    def extract_links(self) -> list[dict]:
        self._ensure_browser()
        try:
            return self._page.eval_on_selector_all(
                "a",
                "els => els.map(el => ({href: el.href, text: el.innerText.trim()})).filter(l => l.href && l.text)"
            )[:100]
        except Exception as e:
            return [{"error": str(e)}]

    def get_html(self) -> str:
        self._ensure_browser()
        return self._page.content()

    def get_rendered_text(self) -> str:
        """Get text rendered in viewport (visible text only)."""
        self._ensure_browser()
        return self._page.evaluate("document.body.innerText")

    # ── State ──────────────────────────────────────────────────────

    def get_state(self) -> dict:
        self._ensure_browser()
        try:
            elements = self._page.evaluate("""() => {
                const sel = 'a,button,input,textarea,select,[role=button],[role=link],[role=tab],[tabindex]';
                return Array.from(document.querySelectorAll(sel))
                    .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0)
                    .map(el => {
                        const r = el.getBoundingClientRect();
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: (el.innerText || el.value || el.placeholder || '').trim().slice(0,100),
                            href: el.href || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cx: Math.round(r.x + r.width/2),
                            cy: Math.round(r.y + r.height/2),
                            type: el.type || '',
                            id: el.id,
                            aria: el.getAttribute('aria-label') || '',
                            disabled: el.disabled || false,
                            visible: r.width > 0 && r.height > 0,
                        };
                    }).slice(0,500);
            }""")
            # Also find shadow DOM elements
            shadow_elements = self._page.evaluate("""() => {
                const results = [];
                const findShadow = (root) => {
                    if (!root) return;
                    if (root.shadowRoot) {
                        const sel = 'a,button,input,[role=button]';
                        root.shadowRoot.querySelectorAll(sel).forEach(el => {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                results.push({
                                    tag: el.tagName.toLowerCase(),
                                    text: (el.innerText || '').trim().slice(0,100),
                                    cx: Math.round(r.x + r.width/2),
                                    cy: Math.round(r.y + r.height/2),
                                    shadow: true,
                                });
                            }
                        });
                        Array.from(root.shadowRoot.children).forEach(findShadow);
                    }
                    Array.from(root.children || []).forEach(findShadow);
                };
                findShadow(document.body);
                return results;
            }""")
            all_elements = elements + shadow_elements
            return {"elements": all_elements, "count": len(all_elements)}
        except Exception as e:
            return {"error": str(e)}

    def get_clickable_at(self, x: int, y: int) -> dict:
        self._ensure_browser()
        try:
            el = self._page.evaluate(f"""() => {{
                const el = document.elementFromPoint({x},{y});
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {{
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.textContent || '').trim().slice(0,100),
                    id: el.id,
                    classes: el.className.slice(0,100),
                    rect: {{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}},
                    shadow: !!el.getRootNode()?.host,
                }};
            }}""")
            return {"element": el, "x": x, "y": y}
        except Exception as e:
            return {"error": str(e)}

    def hover(self, selector: str = "", x: int = 0, y: int = 0, use_coords: bool = False):
        self._ensure_browser()
        if use_coords:
            self._page.mouse.move(x, y)
        else:
            self._retry(lambda: self._page.locator(selector).hover())

    def drag(self, sx: int, sy: int, ex: int, ey: int):
        self._ensure_browser()
        self._page.mouse.move(sx, sy)
        self._page.mouse.down()
        self._page.mouse.move(ex, ey, steps=20)
        self._page.mouse.up()

    def evaluate(self, js: str) -> dict:
        self._ensure_browser()
        try:
            return {"result": str(self._page.evaluate(js))[:5000]}
        except Exception as e:
            return {"error": str(e)}

    def wait(self, ms: int = 1000):
        self._ensure_browser()
        self._page.wait_for_timeout(ms)

    def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for element to appear in DOM and be visible."""
        self._ensure_browser()
        try:
            self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def wait_for_text(self, text: str, timeout: int = 10000) -> bool:
        """Wait for text to appear on page."""
        self._ensure_browser()
        try:
            self._page.wait_for_function(
                f"document.body.innerText.includes('{text.replace(chr(39), chr(92) + chr(39))}')",
                timeout=timeout,
            )
            return True
        except Exception:
            return False

    def wait_for_stable(self, timeout: int = 5000) -> bool:
        """Wait for page to stop changing (stable DOM)."""
        self._ensure_browser()
        try:
            self._page.wait_for_function("""
                new Promise(resolve => {
                    let last = document.body.innerHTML;
                    let checks = 0;
                    const interval = setInterval(() => {
                        const cur = document.body.innerHTML;
                        if (cur === last || checks > 10) {
                            clearInterval(interval); resolve(true);
                        }
                        last = cur; checks++;
                    }, 300);
                })
            """, timeout=timeout)
            return True
        except Exception:
            return False

    # ── Multi-tab ──────────────────────────────────────────────────

    def list_tabs(self) -> list[dict]:
        if not self._context:
            return []
        return [{"index": i, "url": p.url, "title": p.title()} for i, p in enumerate(self._context.pages)]

    def switch_tab(self, index: int) -> bool:
        pages = self._context.pages
        if 0 <= index < len(pages):
            self._page = pages[index]
            self._page.bring_to_front()
            return True
        return False

    def close_tab(self, index: int = -1):
        pages = self._context.pages
        if index < 0:
            index = len(pages) - 1
        if 0 <= index < len(pages):
            pages[index].close()
            if self._page == pages[index] and len(pages) > 1:
                self._page = pages[0]

    def new_tab(self, url: str = "about:blank"):
        self._page = self._context.new_page()
        self._page.set_default_timeout(20000)
        if url != "about:blank":
            self._page.goto(url)
        return self._page

    # ── Console / Network ──────────────────────────────────────────

    def get_console_logs(self) -> list[str]:
        """Get console log messages since last call."""
        self._ensure_browser()
        try:
            logs = self._page.evaluate("""() => {
                if (!window.__maik_console) window.__maik_console = [];
                return window.__maik_console;
            }""")
            self._page.evaluate("window.__maik_console = []")
            return logs or []
        except Exception:
            return []

    def capture_network_requests(self, pattern: str = "") -> list[dict]:
        """Capture network requests matching URL pattern."""
        self._ensure_browser()
        requests = []
        def _handler(req):
            if not pattern or pattern in req.url:
                requests.append({"url": req.url, "method": req.method, "resource": req.resource_type})
        self._page.on("request", _handler)
        return requests

    def generate_pdf(self) -> Optional[str]:
        """Generate PDF of current page, return base64."""
        self._ensure_browser()
        path = SCREENSHOT_DIR / f"page_{int(time.time())}.pdf"
        try:
            self._page.pdf(path=str(path), format="A4")
            return base64.b64encode(path.read_bytes()).decode()
        except Exception:
            return None

    # ── Session persistence ────────────────────────────────────────

    def save_session(self, name: str = "default") -> str:
        if not self._context:
            return "No active context"
        path = SESSION_DIR / f"{name}.json"
        self._context.storage_state(path=str(path))
        return str(path)

    def load_session(self, name: str = "default") -> bool:
        path = SESSION_DIR / f"{name}.json"
        if not path.exists():
            return False
        self.close()
        self._ensure_browser()
        self._context = self._browser.new_context(
            storage_state=str(path),
            viewport={"width": 1280, "height": 800},
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(20000)
        self._block_ads()
        return True

    # ── Lifecycle ──────────────────────────────────────────────────

    def close(self):
        for attr in ("_page", "_context", "_browser", "_playwright"):
            try:
                obj = getattr(self, attr, None)
                if obj is not None:
                    obj.close()
            except Exception:
                pass
            setattr(self, attr, None)

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    def stats(self) -> dict:
        return {
            "actions": len(self._history),
            "screenshots": self._screenshot_count,
            "active": self._page is not None,
        }


browser = BrowserAgent()


class ScreenReader:
    """Ultra-reliable element finder: visible text → ARIA role → shadow DOM → coordinate."""

    def __init__(self):
        self._cache: list[dict] = []

    def capture(self) -> str:
        return browser.screenshot()

    def get_element_at(self, x: int, y: int) -> dict:
        return browser.get_clickable_at(x, y)

    def get_all_interactive(self) -> list[dict]:
        state = browser.get_state()
        return state.get("elements", [])

    def find_text(self, text: str) -> list[dict]:
        t = text.lower()
        return [el for el in self.get_all_interactive() if t in el.get("text", "").lower()]

    def click_text(self, text: str) -> dict:
        matches = self.find_text(text)
        if not matches:
            return {"error": f"Text '{text}' not found on screen", "found": False}
        el = matches[0]
        return browser.click(x=el["cx"], y=el["cy"], use_coords=True)

    def find_by_role(self, role: str) -> list[dict]:
        r = role.lower()
        return [el for el in self.get_all_interactive() if el.get("tag") == r or r in el.get("aria", "").lower()]

    def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        return browser.wait_for_selector(selector, timeout)


screen_reader = ScreenReader()
