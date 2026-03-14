"""Workspaces engine - save and restore window layout configurations."""

import subprocess
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class WindowState:
    window_id: str
    title: str
    pid: int
    x: int
    y: int
    width: int
    height: int
    desktop: int = 0
    is_maximized: bool = False
    is_minimized: bool = False
    process_name: str = ""


@dataclass
class Workspace:
    name: str
    description: str = ""
    windows: List[WindowState] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "windows": [
                {
                    "window_id": w.window_id,
                    "title": w.title,
                    "pid": w.pid,
                    "x": w.x, "y": w.y,
                    "width": w.width, "height": w.height,
                    "desktop": w.desktop,
                    "is_maximized": w.is_maximized,
                    "is_minimized": w.is_minimized,
                    "process_name": w.process_name,
                }
                for w in self.windows
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> "Workspace":
        ws = Workspace(name=data.get("name", ""), description=data.get("description", ""))
        for wd in data.get("windows", []):
            ws.windows.append(WindowState(**wd))
        return ws


WORKSPACES_FILE = Path.home() / ".config" / "linux-powertoys" / "workspaces.json"


def _run(cmd: list, timeout: int = 5) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def capture_window_layout() -> List[WindowState]:
    """Capture current positions of all visible windows using wmctrl."""
    out = _run(["wmctrl", "-l", "-p", "-G"])
    if not out:
        return []

    windows = []
    for line in out.splitlines():
        parts = line.split(None, 8)
        # Format: WID DESKTOP PID X Y W H HOSTMACHINE TITLE
        if len(parts) < 8:
            continue
        try:
            wid = parts[0]
            desktop = int(parts[1])
            pid = int(parts[2])
            x = int(parts[3])
            y = int(parts[4])
            w = int(parts[5])
            h = int(parts[6])
            title = parts[8].strip() if len(parts) > 8 else parts[7].strip()

            # Skip invisible/tiny windows
            if w <= 0 or h <= 0:
                continue
            if title in ("", "(invalid utf-8 string)"):
                continue

            # Get process name
            proc_name = ""
            try:
                with open(f"/proc/{pid}/comm") as f:
                    proc_name = f.read().strip()
            except OSError:
                pass

            # Check window state via xprop
            maximized = minimized = False
            xprop_out = _run(["xprop", "-id", wid, "_NET_WM_STATE"])
            if xprop_out:
                maximized = "_NET_WM_STATE_MAXIMIZED" in xprop_out
                minimized = "_NET_WM_STATE_HIDDEN" in xprop_out

            windows.append(WindowState(
                window_id=wid, title=title, pid=pid,
                x=x, y=y, width=w, height=h,
                desktop=desktop,
                is_maximized=maximized,
                is_minimized=minimized,
                process_name=proc_name,
            ))
        except (ValueError, IndexError):
            continue
    return windows


def restore_window(ws: WindowState) -> bool:
    """Move and resize a window to its saved position."""
    # Try to find window by title (closest match)
    out = _run(["wmctrl", "-l", "-p"])
    if not out:
        return False

    target_id = None
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 5 and ws.title in parts[4]:
            target_id = parts[0]
            break

    if not target_id:
        return False

    # Unmaximize first if needed
    _run(["wmctrl", "-ir", target_id, "-b", "remove,maximized_vert,maximized_horz"])

    # Move and resize: wmctrl -ir WID -e gravity,x,y,w,h
    result = _run([
        "wmctrl", "-ir", target_id, "-e",
        f"0,{ws.x},{ws.y},{ws.width},{ws.height}"
    ])

    if ws.is_maximized:
        _run(["wmctrl", "-ir", target_id, "-b", "add,maximized_vert,maximized_horz"])

    return result is not None


class WorkspacesEngine:
    def __init__(self):
        self._workspaces: List[Workspace] = []
        self._load()

    def _load(self):
        if WORKSPACES_FILE.exists():
            try:
                data = json.loads(WORKSPACES_FILE.read_text())
                self._workspaces = [Workspace.from_dict(d) for d in data]
            except (json.JSONDecodeError, KeyError):
                self._workspaces = []

    def _save(self):
        WORKSPACES_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKSPACES_FILE.write_text(
            json.dumps([ws.to_dict() for ws in self._workspaces], indent=2)
        )

    @property
    def workspaces(self) -> List[Workspace]:
        return self._workspaces

    def capture(self, name: str, description: str = "") -> Workspace:
        """Capture current window layout and save as named workspace."""
        windows = capture_window_layout()
        ws = Workspace(name=name, description=description, windows=windows)
        # Replace existing workspace with same name
        self._workspaces = [w for w in self._workspaces if w.name != name]
        self._workspaces.append(ws)
        self._save()
        return ws

    def restore(self, workspace: Workspace) -> Tuple[int, int]:
        """Restore windows to saved positions. Returns (succeeded, failed) counts."""
        ok = 0
        fail = 0
        for ws in workspace.windows:
            if restore_window(ws):
                ok += 1
            else:
                fail += 1
        return ok, fail

    def delete(self, name: str):
        self._workspaces = [w for w in self._workspaces if w.name != name]
        self._save()

    def rename(self, old_name: str, new_name: str):
        for ws in self._workspaces:
            if ws.name == old_name:
                ws.name = new_name
                break
        self._save()

    def get_current_windows(self) -> List[WindowState]:
        return capture_window_layout()
