"""AlwaysOnTop engine - pin windows on top using EWMH/wmctrl."""

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class ManagedWindow:
    window_id: str
    title: str
    pid: int
    pinned: bool = False


def _run(cmd: list, timeout: int = 3) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def list_windows() -> List[ManagedWindow]:
    """List all visible windows via wmctrl."""
    out = _run(["wmctrl", "-l", "-p"])
    if not out:
        return []
    windows = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 5:
            wid = parts[0]
            try:
                pid = int(parts[2])
            except ValueError:
                pid = 0
            title = parts[4].strip()
            if title and title != "(invalid utf-8 string)":
                windows.append(ManagedWindow(window_id=wid, title=title, pid=pid))
    return windows


def set_window_on_top(window_id: str, on_top: bool) -> bool:
    """Set or remove always-on-top property using wmctrl EWMH."""
    action = "add" if on_top else "remove"
    result = _run([
        "wmctrl", "-ir", window_id, "-b", f"{action},above"
    ])
    return result is not None


def get_focused_window_id() -> Optional[str]:
    """Get the currently focused window ID."""
    out = _run(["xdotool", "getactivewindow"])
    return out.strip() if out else None


def get_focused_window_hex() -> Optional[str]:
    """Return focused window ID as hex string compatible with wmctrl."""
    dec_id = get_focused_window_id()
    if dec_id:
        try:
            return hex(int(dec_id))
        except ValueError:
            pass
    return None


class AlwaysOnTopEngine:
    def __init__(self):
        self._pinned: Dict[str, ManagedWindow] = {}

    def get_windows(self) -> List[ManagedWindow]:
        windows = list_windows()
        for w in windows:
            w.pinned = w.window_id in self._pinned
        return windows

    def pin(self, window: ManagedWindow) -> bool:
        ok = set_window_on_top(window.window_id, True)
        if ok:
            window.pinned = True
            self._pinned[window.window_id] = window
        return ok

    def unpin(self, window: ManagedWindow) -> bool:
        ok = set_window_on_top(window.window_id, False)
        if ok:
            window.pinned = False
            self._pinned.pop(window.window_id, None)
        return ok

    def toggle(self, window: ManagedWindow) -> bool:
        if window.pinned:
            return self.unpin(window)
        return self.pin(window)

    def pin_focused_window(self) -> Optional[ManagedWindow]:
        """Pin the currently focused window."""
        wid = get_focused_window_hex()
        if not wid:
            return None
        windows = list_windows()
        for w in windows:
            if w.window_id.lower() == wid.lower():
                self.pin(w)
                return w
        # Create a placeholder if not in list
        placeholder = ManagedWindow(window_id=wid, title="Focused Window", pid=0)
        self.pin(placeholder)
        return placeholder

    def unpin_all(self):
        for w in list(self._pinned.values()):
            set_window_on_top(w.window_id, False)
        self._pinned.clear()

    @property
    def pinned_count(self) -> int:
        return len(self._pinned)
