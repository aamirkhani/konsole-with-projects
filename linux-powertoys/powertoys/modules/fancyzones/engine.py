"""FancyZones engine - window tiling layout management."""

import subprocess
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict


@dataclass
class Zone:
    """A rectangular screen zone (in percentage of screen)."""
    x: float       # 0.0 - 1.0
    y: float
    width: float
    height: float
    name: str = ""

    def to_pixels(self, screen_w: int, screen_h: int) -> Tuple[int, int, int, int]:
        return (
            int(self.x * screen_w),
            int(self.y * screen_h),
            int(self.width * screen_w),
            int(self.height * screen_h),
        )


@dataclass
class Layout:
    name: str
    zones: List[Zone] = field(default_factory=list)
    icon: str = "view-grid-symbolic"

    @classmethod
    def columns(cls, n: int) -> "Layout":
        """Split screen into N equal columns."""
        w = 1.0 / n
        zones = [Zone(x=i * w, y=0, width=w, height=1.0, name=f"Col {i+1}") for i in range(n)]
        return cls(name=f"{n} Columns", zones=zones)

    @classmethod
    def rows(cls, n: int) -> "Layout":
        h = 1.0 / n
        zones = [Zone(x=0, y=i * h, width=1.0, height=h, name=f"Row {i+1}") for i in range(n)]
        return cls(name=f"{n} Rows", zones=zones)

    @classmethod
    def grid(cls, cols: int, rows: int) -> "Layout":
        w, h = 1.0 / cols, 1.0 / rows
        zones = []
        for row in range(rows):
            for col in range(cols):
                zones.append(Zone(x=col * w, y=row * h, width=w, height=h, name=f"R{row+1}C{col+1}"))
        return cls(name=f"{cols}×{rows} Grid", zones=zones)

    @classmethod
    def primary_secondary(cls) -> "Layout":
        return cls(name="Primary + Secondary", zones=[
            Zone(x=0, y=0, width=0.6, height=1.0, name="Primary"),
            Zone(x=0.6, y=0, width=0.4, height=0.5, name="Top Right"),
            Zone(x=0.6, y=0.5, width=0.4, height=0.5, name="Bottom Right"),
        ])

    @classmethod
    def three_column(cls) -> "Layout":
        return cls(name="Three Column", zones=[
            Zone(x=0, y=0, width=0.25, height=1.0, name="Left"),
            Zone(x=0.25, y=0, width=0.5, height=1.0, name="Center"),
            Zone(x=0.75, y=0, width=0.25, height=1.0, name="Right"),
        ])


BUILTIN_LAYOUTS = [
    Layout.columns(2),
    Layout.columns(3),
    Layout.columns(4),
    Layout.rows(2),
    Layout.rows(3),
    Layout.grid(2, 2),
    Layout.grid(3, 2),
    Layout.primary_secondary(),
    Layout.three_column(),
    Layout(name="Full Screen", zones=[Zone(0, 0, 1, 1, "Full")]),
]


def get_screen_size() -> Tuple[int, int]:
    """Get primary monitor dimensions."""
    try:
        out = subprocess.check_output(
            ["xdpyinfo"], text=True, timeout=3
        )
        import re
        m = re.search(r"dimensions:\s+(\d+)x(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    # Try xrandr
    try:
        out = subprocess.check_output(["xrandr", "--current"], text=True, timeout=3)
        import re
        m = re.search(r"(\d+)x(\d+)\+0\+0", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1920, 1080  # fallback


def get_active_window_id() -> Optional[str]:
    """Get X11 window ID of the focused window as a hex string (wmctrl-compatible)."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            dec = result.stdout.strip()
            return hex(int(dec))   # convert decimal → hex for wmctrl
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    # Fallback: ask wmctrl for the active window
    try:
        result = subprocess.run(
            ["wmctrl", "-a", ":ACTIVE:", "-v"],
            capture_output=True, text=True, timeout=3,
        )
        # Try xprop _NET_ACTIVE_WINDOW
        result2 = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True, text=True, timeout=3,
        )
        if result2.returncode == 0:
            import re
            m = re.search(r"0x[0-9a-fA-F]+", result2.stdout)
            if m:
                return m.group(0)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def move_window_to_zone(window_id: str, zone: Zone, screen_w: int, screen_h: int, gap: int = 4):
    """Move/resize a window to fill a zone using wmctrl or xdotool."""
    x, y, w, h = zone.to_pixels(screen_w, screen_h)
    # Apply gap
    x += gap; y += gap; w -= gap * 2; h -= gap * 2

    # Unmaximize first — a maximized window ignores move/resize
    try:
        subprocess.run(
            ["wmctrl", "-ir", window_id, "-b", "remove,maximized_vert,maximized_horz"],
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try wmctrl first (expects hex window ID)
    try:
        r = subprocess.run(
            ["wmctrl", "-ir", window_id, "-e", f"0,{x},{y},{w},{h}"],
            timeout=3,
        )
        if r.returncode == 0:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: xdotool (accepts decimal or hex)
    try:
        subprocess.run(
            ["xdotool", "windowmove", window_id, str(x), str(y)],
            timeout=3,
        )
        subprocess.run(
            ["xdotool", "windowsize", window_id, str(w), str(h)],
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


class FancyZonesEngine:
    def __init__(self):
        self.layouts = list(BUILTIN_LAYOUTS)
        self.active_layout: Optional[Layout] = None
        self.gap = 4  # pixels between zones
        self._screen_size = get_screen_size()

    @property
    def screen_w(self) -> int:
        return self._screen_size[0]

    @property
    def screen_h(self) -> int:
        return self._screen_size[1]

    def refresh_screen_size(self):
        self._screen_size = get_screen_size()

    def activate_layout(self, layout: Layout):
        self.active_layout = layout

    def snap_active_window(self, zone_index: int) -> bool:
        """Snap the currently focused window into zone[zone_index]."""
        if not self.active_layout or zone_index >= len(self.active_layout.zones):
            return False
        win_id = get_active_window_id()
        if not win_id:
            return False
        zone = self.active_layout.zones[zone_index]
        move_window_to_zone(win_id, zone, self.screen_w, self.screen_h, self.gap)
        return True

    def snap_window(self, window_id: str, zone_index: int) -> bool:
        if not self.active_layout or zone_index >= len(self.active_layout.zones):
            return False
        zone = self.active_layout.zones[zone_index]
        move_window_to_zone(window_id, zone, self.screen_w, self.screen_h, self.gap)
        return True

    def tile_all_windows(self):
        """Distribute all open windows across the active layout zones."""
        if not self.active_layout:
            return
        try:
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True, text=True, timeout=5,
            )
            windows = [line.split()[0] for line in result.stdout.splitlines()]
            zones = self.active_layout.zones
            for i, win_id in enumerate(windows):
                zone = zones[i % len(zones)]
                move_window_to_zone(win_id, zone, self.screen_w, self.screen_h, self.gap)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def add_custom_layout(self, layout: Layout):
        self.layouts.append(layout)

    def remove_layout(self, name: str):
        self.layouts = [l for l in self.layouts if l.name != name]
