"""ScreenRuler engine - pixel measurement utilities."""

import subprocess
from typing import Tuple, Optional


class ScreenRulerEngine:
    UNITS = ["Pixels", "Inches", "Centimeters", "Points (pt)", "Picas"]

    def __init__(self, dpi: int = 96):
        self.dpi = dpi
        self._detect_dpi()

    def _detect_dpi(self):
        """Try to detect the actual screen DPI."""
        try:
            result = subprocess.run(["xdpyinfo"], capture_output=True, text=True, timeout=3)
            import re
            m = re.search(r"resolution:\s+(\d+)x(\d+)", result.stdout)
            if m:
                self.dpi = int(m.group(1))
        except Exception:
            pass

    def convert(self, pixels: float, unit: str) -> str:
        """Convert pixel measurement to a given unit."""
        if unit == "Pixels":
            return f"{pixels:.0f} px"
        elif unit == "Inches":
            val = pixels / self.dpi
            return f"{val:.3f} in"
        elif unit == "Centimeters":
            val = pixels / self.dpi * 2.54
            return f"{val:.3f} cm"
        elif unit == "Points (pt)":
            val = pixels / self.dpi * 72
            return f"{val:.1f} pt"
        elif unit == "Picas":
            val = pixels / self.dpi * 6
            return f"{val:.2f} pc"
        return f"{pixels:.0f} px"

    def pixels_between(self, x1: int, y1: int, x2: int, y2: int) -> float:
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def get_cursor_pos(self) -> Optional[Tuple[int, int]]:
        """Get the current mouse cursor position."""
        try:
            result = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, timeout=3)
            import re
            m = re.match(r"x:(\d+) y:(\d+)", result.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None
