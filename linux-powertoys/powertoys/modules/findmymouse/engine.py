"""FindMyMouse engine - locate cursor with spotlight/sonar effect."""

import subprocess
import threading
from typing import Optional, Tuple


def get_cursor_position() -> Optional[Tuple[int, int]]:
    """Return (x, y) of current cursor position using xdotool or xdpyinfo."""
    try:
        r = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            pos = {}
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    pos[k.strip()] = v.strip()
            x = int(pos.get("X", 0))
            y = int(pos.get("Y", 0))
            return x, y
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # Fallback: xdpyinfo doesn't give cursor pos, try python-xlib approach
    try:
        r = subprocess.run(
            ["python3.12", "-c",
             "import Xlib.display; d=Xlib.display.Display(); r=d.screen().root;"
             "p=r.query_pointer(); print(p.root_x, p.root_y)"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            x, y = map(int, r.stdout.strip().split())
            return x, y
    except Exception:
        pass
    return None


def get_screen_size() -> Tuple[int, int]:
    """Return (width, height) of primary screen."""
    try:
        r = subprocess.run(
            ["xdpyinfo"], capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "dimensions:" in line:
                    # "  dimensions:    1920x1080 pixels ..."
                    part = line.split(":")[1].strip().split()[0]
                    w, h = part.split("x")
                    return int(w), int(h)
    except Exception:
        pass
    return 1920, 1080


class FindMyMouseEngine:
    def __init__(self):
        self.spotlight_radius: int = 100
        self.overlay_opacity: float = 0.7
        self.animation_duration_ms: int = 800
        self.shake_to_activate: bool = False

    def get_cursor_position(self) -> Optional[Tuple[int, int]]:
        return get_cursor_position()

    def get_screen_size(self) -> Tuple[int, int]:
        return get_screen_size()
