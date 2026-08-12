"""Unified Vision — merges browser + computer use agents into one screen perception system.

Both Browser Agent and Computer Use Agent now share the same PixelVision engine.
The UnifiedVision class provides a single API for:
- Screen/element detection (works on both desktop and web)
- Pixel-perfect coordinate finding
- Icon/button/text recognition
- Cross-platform: works on browser viewport AND desktop screen
"""
from __future__ import annotations
from pixel_vision import PixelVision, VisionElement, pixel_vision
from typing import Optional


class UnifiedVision:
    """Single vision system for both browser and desktop.

    Browser Agent uses: viewport-based detection
    Computer Use Agent uses: full-screen detection
    Both use the same detection algorithms.
    """

    def __init__(self):
        self._engine = pixel_vision  # Shared global instance
        self._mode = "desktop"  # "desktop" or "browser"
        self._viewport_offset = {"x": 0, "y": 0, "width": 1280, "height": 800}

    def set_browser_viewport(self, x: int, y: int, width: int, height: int):
        """Set browser viewport region for coordinate mapping."""
        self._mode = "browser"
        self._viewport_offset = {"x": x, "y": y, "width": width, "height": height}

    def set_desktop_mode(self):
        """Switch to full desktop mode."""
        self._mode = "desktop"

    def _adjust_coords(self, x: int, y: int) -> tuple[int, int]:
        """Convert browser-relative coords to screen coords."""
        if self._mode == "browser":
            return x + self._viewport_offset["x"], y + self._viewport_offset["y"]
        return x, y

    def get_element_at(self, x: int, y: int) -> Optional[VisionElement]:
        """Get element at pixel coordinates (mode-aware)."""
        sx, sy = self._adjust_coords(x, y)
        return self._engine.get_element_at(sx, sy)

    def find_interactable_by_text(self, text: str) -> Optional[VisionElement]:
        """Find button/link/input by visible text."""
        return self._engine.find_interactable_by_text(text)

    def find_icon_by_image(self, template_path: str, confidence: float = 0.7) -> Optional[VisionElement]:
        """Find icon on screen by matching template image."""
        return self._engine.find_icon_by_image(template_path, confidence)

    def find_all_icons(self, template_path: str, confidence: float = 0.7) -> list[VisionElement]:
        """Find all occurrences of icon on screen."""
        return self._engine.find_all_icons(template_path, confidence)

    def detect_elements(self) -> list[VisionElement]:
        """Detect ALL visual elements on screen."""
        return self._engine.detect_elements()

    def describe_screen(self) -> dict:
        """Full screen description."""
        return self._engine.describe_screen()

    def get_pixel_color_at(self, x: int, y: int) -> Optional[str]:
        """Get hex color of pixel at coordinates."""
        sx, sy = self._adjust_coords(x, y)
        return self._engine.get_pixel_color_at(sx, sy)

    def detect_color_palette(self) -> list[dict]:
        """Extract dominant colors from screen."""
        return self._engine.detect_color_palette()

    def detect_layout_grid(self) -> list:
        """Detect screen regions."""
        return self._engine.detect_layout_grid()

    def screenshot_b64(self) -> str:
        return self._engine.screenshot_b64()

    def get_clickable_at(self, x: int, y: int) -> Optional[VisionElement]:
        """Get clickable element at point."""
        el = self.get_element_at(x, y)
        if el and el.is_interactive:
            return el
        return None

    def find_best_click_point(self, text: str) -> Optional[dict]:
        """Find the best click point for a text label (button/link)."""
        el = self.find_interactable_by_text(text)
        if el:
            sx, sy = self._adjust_coords(el.center_x, el.center_y)
            return {"x": sx, "y": sy, "element": el.type, "confidence": el.confidence}
        return None

    def detect_ui_changes(self, prev_elements: list[VisionElement]) -> list[dict]:
        """Detect what changed between two screen captures."""
        current = self.detect_elements()
        changes = []
        prev_set = {(e.x, e.y, e.width, e.height) for e in prev_elements}
        for el in current:
            key = (el.x, el.y, el.width, el.height)
            if key not in prev_set:
                changes.append({
                    "type": el.type, "text": el.text,
                    "x": el.x, "y": el.y,
                    "center_x": el.center_x, "center_y": el.center_y,
                })
        return changes


unified_vision = UnifiedVision()
