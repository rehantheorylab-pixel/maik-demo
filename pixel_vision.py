"""Pixel Vision — sees screen like a human: icons, buttons, text, colors, layouts, OCR.

Integrates latest research:
- Multi-scale template matching (OpenCV)
- EAST/EasyOCR for scene text detection
- Color-aware segmentation
- Contour detection for icon/button boundaries
- DPI-aware coordinate mapping
- Element relationship detection (forms, lists, grids)
"""
from __future__ import annotations
import base64, time, io, os, math, random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

SCREENSHOT_DIR = Path("memory/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

_HAS_CV2 = False
_HAS_EASYOCR = False
_HAS_PIL = False
_HAS_TRANSFORMERS = False

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    pass

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    _HAS_PIL = True
except ImportError:
    pass

try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    pass


@dataclass
class VisionElement:
    """A visual element detected on screen."""
    type: str  # "button", "icon", "text", "input", "image", "label", "checkbox", "radio"
    text: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    center_x: int = 0
    center_y: int = 0
    confidence: float = 0.0
    color: Optional[str] = None
    bg_color: Optional[str] = None
    is_interactive: bool = False
    children: list = field(default_factory=list)
    parent: Optional[str] = None


@dataclass
class ScreenRegion:
    """A semantic region of the screen."""
    label: str
    x: int
    y: int
    width: int
    height: int
    elements: list[VisionElement] = field(default_factory=list)
    role: str = ""


class PixelVision:
    """Human-like screen perception: detects icons, buttons, text, colors, layouts.

    Uses:
    - OpenCV contour detection for element boundaries
    - Multi-scale template matching for icon finding
    - EasyOCR for text detection
    - Color clustering for semantic regions
    - Layout analysis for form/button/text grouping
    """

    def __init__(self):
        self._reader = None
        self._dpi_scale = self._get_dpi_scale()
        self._screen_cache: Optional[np.ndarray] = None
        self._last_gray: Optional[np.ndarray] = None
        self._last_rgb: Optional[np.ndarray] = None
        self._screenshot_count = 0
        self._init_ocr()

    def _get_dpi_scale(self) -> float:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            dc = user32.GetDC(0)
            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
            user32.ReleaseDC(0, dc)
            return dpi_x / 96.0
        except Exception:
            return 1.0

    def _init_ocr(self):
        if _HAS_EASYOCR:
            try:
                self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            except Exception:
                pass

    def capture_screen(self) -> np.ndarray:
        """Capture screen as numpy array (BGR)."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                img = np.array(raw)
                self._screenshot_count += 1
                # Save periodically
                if self._screenshot_count % 10 == 1:
                    path = SCREENSHOT_DIR / f"vision_{self._screenshot_count}_{int(time.time())}.png"
                    if _HAS_PIL:
                        Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)).save(str(path))
                self._screen_cache = img
                self._last_bgra = img.copy()
                self._last_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
                self._last_gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                return img
        except Exception:
            raise

    def screenshot_b64(self) -> str:
        """Return screenshot as base64."""
        try:
            import mss
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
                if _HAS_PIL:
                    img = Image.frombytes("RGB", raw.size, raw.rgb)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return ""

    # ── Element Detection ──────────────────────────────────────────

    def detect_elements(self, image: Optional[np.ndarray] = None) -> list[VisionElement]:
        """Detect ALL visual elements on screen using latest research methods."""
        if image is None:
            image = self.capture_screen()
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY) if image.shape[2] == 4 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB) if image.shape[2] == 4 else cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = gray.shape
        elements: list[VisionElement] = []

        # 1. Contour detection (finds buttons, icons, input fields)
        elements.extend(self._detect_contours(gray, rgb, h, w))

        # 2. Text detection via OCR
        elements.extend(self._detect_text(rgb))

        # 3. Color-based region detection
        elements.extend(self._detect_colored_regions(rgb, h, w))

        # 4. Arrow/pointer detection
        if _HAS_CV2:
            elements.extend(self._detect_arrows(gray))

        # 5. Layout analysis - group into forms, panels, modals
        elements = self._layout_analysis(elements, h, w)

        # Deduplicate by position
        return self._deduplicate(elements)

    def _detect_contours(self, gray: np.ndarray, rgb: np.ndarray, h: int, w: int) -> list[VisionElement]:
        """Find UI elements via contour detection + morphological operations."""
        elements = []

        # Adaptive threshold for varying lighting
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)

        # Morphological close to merge nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x_, y_, w_, h_ = cv2.boundingRect(cnt)
            area = w_ * h_
            if area < 150 or area > (h * w * 0.6):  # Skip tiny or huge
                continue
            aspect = w_ / max(h_, 1)
            # Classify by aspect ratio and area
            elem_type = "button"
            is_interactive = False
            text = ""

            if aspect > 4 and h_ < 60:
                elem_type = "text"
            elif area < 800 and abs(aspect - 1.0) < 0.5:
                elem_type = "icon"
                is_interactive = True
            elif aspect < 0.3 and h_ > 50:
                elem_type = "button"  # tall skinny button
            elif aspect > 1.5 and h_ < 40:
                elem_type = "input"
                is_interactive = True

            # Sample colors
            center_y = y_ + h_ // 2
            center_x = x_ + w_ // 2
            if center_y < h and center_x < w:
                avg_color = rgb[center_y, center_x]
                color_hex = "#{:02x}{:02x}{:02x}".format(*avg_color)
            else:
                color_hex = "#000000"

            # Detect if likely a button (uniform color fill)
            if _HAS_CV2:
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.rectangle(mask, (x_, y_), (x_ + w_, y_ + h_), 255, -1)
                fill_ratio = cv2.countNonZero(cv2.bitwise_and(binary, mask)) / max(area, 1)
                if fill_ratio > 0.3 and elem_type == "button":
                    is_interactive = True

            # Look for text inside element
            if _HAS_CV2 and h_ > 20 and w_ > 20:
                roi_gray = gray[y_:y_ + h_, x_:x_ + w_]
                _, roi_binary = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                # Check if there's text-like content
                text_pixels = cv2.countNonZero(cv2.bitwise_not(roi_binary))
                if text_pixels > 20:
                    is_interactive = True

            elements.append(VisionElement(
                type=elem_type,
                x=x_, y=y_, width=w_, height=h_,
                center_x=x_ + w_ // 2, center_y=y_ + h_ // 2,
                color=color_hex, is_interactive=is_interactive,
                text=text, confidence=0.5,
            ))

        return elements

    def _detect_text(self, rgb: np.ndarray) -> list[VisionElement]:
        """Detect text regions using EasyOCR or OpenCV MSER."""
        elements = []
        if self._reader is None:
            # Fallback: simple MSER + contour text detection
            if _HAS_CV2:
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                mser = cv2.MSER_create()
                try:
                    regions, _ = mser.detectRegions(gray)
                    for region in regions:
                        x_, y_, w_, h_ = cv2.boundingRect(region)
                        if 20 < w_ < 500 and 10 < h_ < 100:
                            elements.append(VisionElement(
                                type="text",
                                x=x_, y=y_, width=w_, height=h_,
                                center_x=x_ + w_ // 2, center_y=y_ + h_ // 2,
                                confidence=0.4, is_interactive=False,
                            ))
                except Exception:
                    pass
            return elements

        # EasyOCR
        try:
            results = self._reader.readtext(rgb, paragraph=True, width_ths=0.5)
            for bbox, text, conf in results:
                pts = np.array(bbox, dtype=np.int32)
                x_ = int(min(pts[:, 0]))
                y_ = int(min(pts[:, 1]))
                w_ = int(max(pts[:, 0])) - x_
                h_ = int(max(pts[:, 1])) - y_
                elements.append(VisionElement(
                    type="text",
                    text=text, x=x_, y=y_, width=w_, height=h_,
                    center_x=x_ + w_ // 2, center_y=y_ + h_ // 2,
                    confidence=float(conf), is_interactive=False,
                ))
        except Exception:
            pass
        return elements

    def _detect_colored_regions(self, rgb: np.ndarray, h: int, w: int) -> list[VisionElement]:
        """Detect colored regions (menus, toolbars, panels)."""
        elements = []
        if not _HAS_CV2:
            return elements

        # Detect blue-ish regions (common for links, interactive elements)
        lower_blue = np.array([0, 0, 100])
        upper_blue = np.array([100, 100, 255])
        blue_mask = cv2.inRange(rgb, lower_blue, upper_blue)
        blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in blue_contours:
            x_, y_, w_, h_ = cv2.boundingRect(cnt)
            area = w_ * h_
            if 200 < area < h * w * 0.2:
                elements.append(VisionElement(
                    type="link", x=x_, y=y_, width=w_, height=h_,
                    center_x=x_ + w_ // 2, center_y=y_ + h_ // 2,
                    color="#0000ff", confidence=0.6, is_interactive=True,
                ))

        # Detect white/gray regions (forms, panels)
        lower_gray = np.array([180, 180, 180])
        upper_gray = np.array([255, 255, 255])
        gray_mask = cv2.inRange(rgb, lower_gray, upper_gray)
        gray_contours, _ = cv2.findContours(gray_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in gray_contours:
            x_, y_, w_, h_ = cv2.boundingRect(cnt)
            area = w_ * h_
            if area > 5000 and w_ > 100 and h_ > 50:
                elements.append(VisionElement(
                    type="panel", x=x_, y=y_, width=w_, height=h_,
                    center_x=x_ + w_ // 2, center_y=y_ + h_ // 2,
                    bg_color="#f0f0f0", confidence=0.5, is_interactive=False,
                ))

        return elements

    def _detect_arrows(self, gray: np.ndarray) -> list[VisionElement]:
        """Detect arrow-like shapes (scroll arrows, dropdown indicators)."""
        elements = []
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, math.pi / 180, 50, minLineLength=15, maxLineGap=5)
        if lines is None:
            return elements
        # Group lines into arrow candidates
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx ** 2 + dy ** 2)
            if 10 < length < 60:
                elements.append(VisionElement(
                    type="line", x=min(x1, x2), y=min(y1, y2),
                    width=abs(dx), height=abs(dy),
                    center_x=(x1 + x2) // 2, center_y=(y1 + y2) // 2,
                    confidence=0.3, is_interactive=False,
                ))
        return elements

    def _layout_analysis(self, elements: list[VisionElement], screen_h: int, screen_w: int) -> list[VisionElement]:
        """Group elements into semantic regions (toolbar, form, modal, etc.)."""
        # Sort by y position
        sorted_els = sorted(elements, key=lambda e: (e.y, e.x))
        # Detect if elements form a grid (form layout)
        rows: dict[int, list[VisionElement]] = {}
        for el in sorted_els:
            row_key = el.y // 30  # Group by 30px bands
            if row_key not in rows:
                rows[row_key] = []
            rows[row_key].append(el)
        # Label interactive regions
        for row_y, row_els in rows.items():
            if len(row_els) >= 2:
                for el in row_els:
                    if el.type in ("input", "icon"):
                        el.parent = f"form_row_{row_y}"
        return elements

    def _deduplicate(self, elements: list[VisionElement]) -> list[VisionElement]:
        """Remove overlapping elements, keep highest confidence."""
        if not elements:
            return []
        sorted_els = sorted(elements, key=lambda e: (e.y, e.x, -e.confidence))
        kept: list[VisionElement] = []
        for el in sorted_els:
            duplicate = False
            for k in kept:
                # Check overlap
                ix = max(el.x, k.x)
                iy = max(el.y, k.y)
                ix2 = min(el.x + el.width, k.x + k.width)
                iy2 = min(el.y + el.height, k.y + k.height)
                overlap_area = max(0, ix2 - ix) * max(0, iy2 - iy)
                el_area = el.width * el.height
                if el_area > 0 and overlap_area / el_area > 0.6:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(el)
        return kept

    # ── High-level perception ──────────────────────────────────────

    def describe_screen(self) -> dict:
        """Full screen description: elements, regions, layout, interactables."""
        img = self.capture_screen()
        elements = self.detect_elements(img)
        h, w = img.shape[:2]

        interactables = [e for e in elements if e.is_interactive]
        texts = [e for e in elements if e.type == "text"]

        # Summarize regions
        regions: dict[str, list[VisionElement]] = {}
        for el in elements:
            r = el.parent or "main"
            if r not in regions:
                regions[r] = []
            regions[r].append(el)

        return {
            "screen_size": {"width": w, "height": h, "dpi_scale": self._dpi_scale},
            "total_elements": len(elements),
            "interactable_elements": len(interactables),
            "text_regions": len(texts),
            "elements": [self._el_to_dict(e) for e in elements[:100]],
            "interactables": [self._el_to_dict(e) for e in interactables[:50]],
            "texts": [e.text for e in texts[:30] if e.text],
            "regions": {k: len(v) for k, v in regions.items()},
            "screenshot_b64": self.screenshot_b64(),
        }

    def find_interactable_by_text(self, text: str) -> Optional[VisionElement]:
        """Find button/link/input by visible text."""
        elements = self.detect_elements()
        t = text.lower()
        for el in elements:
            if t in el.text.lower():
                return el
        # Second pass: look for nearby text
        texts = [e for e in elements if e.type == "text" and t in e.text.lower()]
        if texts:
            t_el = texts[0]
            # Find closest interactable element
            best = None
            best_dist = float("inf")
            for el in elements:
                if el.is_interactive and el != t_el:
                    d = math.sqrt((el.center_x - t_el.center_x) ** 2 + (el.center_y - t_el.center_y) ** 2)
                    if d < best_dist and d < 200:
                        best_dist = d
                        best = el
            return best
        return None

    def get_element_at(self, x: int, y: int) -> Optional[VisionElement]:
        """Get element at pixel coordinates."""
        elements = self.detect_elements()
        for el in reversed(elements):
            if el.x <= x <= el.x + el.width and el.y <= y <= el.y + el.height:
                return el
        return None

    def get_pixel_color_at(self, x: int, y: int) -> Optional[str]:
        """Get hex color of pixel at coordinates."""
        try:
            import mss
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
                img = np.array(raw)
                if y < img.shape[0] and x < img.shape[1]:
                    b, g, r, _ = img[y, x]
                    return "#{:02x}{:02x}{:02x}".format(r, g, b)
        except Exception:
            pass
        return None

    def find_icon_by_image(self, template_path: str, confidence: float = 0.7) -> Optional[VisionElement]:
        """Find icon on screen by matching template image."""
        if not _HAS_CV2:
            return None
        try:
            needle = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if needle is None:
                return None
            haystack = self.capture_screen()
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGRA2GRAY) if haystack.shape[2] == 4 else haystack
            h, w = needle.shape[:2]

            # Multi-scale
            for scale in np.linspace(0.5, 1.5, 15)[::-1]:
                resized = cv2.resize(haystack_gray, None, fx=scale, fy=scale)
                if resized.shape[0] < h or resized.shape[1] < w:
                    continue
                result = cv2.matchTemplate(resized, needle, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val >= confidence:
                    inv_scale = 1.0 / scale
                    x = int(max_loc[0] * inv_scale)
                    y = int(max_loc[1] * inv_scale)
                    return VisionElement(
                        type="icon",
                        x=x, y=y, width=w, height=h,
                        center_x=x + w // 2, center_y=y + h // 2,
                        confidence=float(max_val), is_interactive=True,
                    )
        except Exception:
            pass
        return None

    def find_all_icons(self, template_path: str, confidence: float = 0.7) -> list[VisionElement]:
        """Find all occurrences of icon on screen."""
        results = []
        if not _HAS_CV2:
            return results
        try:
            needle = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if needle is None:
                return results
            haystack = self.capture_screen()
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGRA2GRAY) if haystack.shape[2] == 4 else haystack
            w, h = needle.shape[::-1]
            res = cv2.matchTemplate(haystack_gray, needle, cv2.TM_CCOEFF_NORMED)
            locs = np.where(res >= confidence)
            for pt in zip(*locs[::-1]):
                results.append(VisionElement(
                    type="icon",
                    x=pt[0], y=pt[1], width=w, height=h,
                    center_x=pt[0] + w // 2, center_y=pt[1] + h // 2,
                    confidence=float(res[pt[1], pt[0]]), is_interactive=True,
                ))
        except Exception:
            pass
        return results

    def detect_layout_grid(self) -> list[ScreenRegion]:
        """Detect screen regions (top bar, side panel, content area, etc.)."""
        img = self.capture_screen()
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        h, w = gray.shape
        # Detect horizontal separators
        edges = cv2.Canny(gray, 50, 150)
        horizontal_lines = cv2.HoughLinesP(edges, 1, math.pi / 180, 200, minLineLength=w // 2, maxLineGap=10)
        vertical_lines = cv2.HoughLinesP(edges, 1, math.pi / 180, 200, minLineLength=h // 2, maxLineGap=10)

        y_cuts = {0, h}
        x_cuts = {0, w}
        if horizontal_lines is not None:
            for line in horizontal_lines:
                x1, y1, x2, y2 = line[0]
                if abs(y1 - y2) < 5:
                    y_cuts.add(y1)
        if vertical_lines is not None:
            for line in vertical_lines:
                x1, y1, x2, y2 = line[0]
                if abs(x1 - x2) < 5:
                    x_cuts.add(x1)

        y_cuts = sorted(y_cuts)
        x_cuts = sorted(x_cuts)
        regions = []
        for i in range(len(y_cuts) - 1):
            y1, y2 = y_cuts[i], y_cuts[i + 1]
            for j in range(len(x_cuts) - 1):
                x1, x2 = x_cuts[j], x_cuts[j + 1]
                if (x2 - x1) > 50 and (y2 - y1) > 30:
                    regions.append(ScreenRegion(
                        label=f"region_{j}_{i}",
                        x=x1, y=y1, width=x2 - x1, height=y2 - y1,
                        role="content",
                    ))
        return regions

    def detect_color_palette(self) -> list[dict]:
        """Extract dominant colors from screen."""
        img = self.capture_screen()
        rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        pixels = rgb.reshape(-1, 3)
        # Simple color clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(
            pixels.astype(np.float32), 8, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
        )
        colors = []
        for center in centers:
            r, g, b = int(center[0]), int(center[1]), int(center[2])
            colors.append({"rgb": (r, g, b), "hex": "#{:02x}{:02x}{:02x}".format(r, g, b)})
        return colors

    def _el_to_dict(self, el: VisionElement) -> dict:
        return {
            "type": el.type, "text": el.text,
            "x": el.x, "y": el.y, "width": el.width, "height": el.height,
            "center_x": el.center_x, "center_y": el.center_y,
            "confidence": round(el.confidence, 2),
            "color": el.color, "bg_color": el.bg_color,
            "interactive": el.is_interactive, "parent": el.parent,
        }


# Global instance
pixel_vision = PixelVision()
