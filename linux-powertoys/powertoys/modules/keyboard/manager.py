"""Keyboard Manager engine - key remapping via xmodmap/keyd."""

import subprocess
import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class KeyRemap:
    from_key: str    # e.g. "CapsLock", "ctrl+c"
    to_key: str      # e.g. "Escape", "ctrl+v"
    description: str = ""
    enabled: bool = True


@dataclass
class ShortcutRemap:
    from_shortcut: str   # e.g. "ctrl+c"
    to_shortcut: str     # e.g. "ctrl+insert"
    app_context: str = ""  # empty = all apps
    description: str = ""
    enabled: bool = True


# Common key names for xmodmap
XMODMAP_KEY_NAMES = [
    "Escape", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "BackSpace", "Tab", "Return", "space", "CapsLock", "Shift_L", "Shift_R",
    "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Delete", "Insert", "Home", "End", "Prior", "Next",
    "Left", "Right", "Up", "Down",
    "Print", "Scroll_Lock", "Pause",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "semicolon", "comma", "period", "slash", "backslash", "minus", "equal",
    "bracketleft", "bracketright", "apostrophe", "grave",
]

CONFIG_PATH = Path.home() / ".config" / "linux-powertoys" / "keyboard.json"


class KeyboardEngine:
    def __init__(self):
        self.key_remaps: List[KeyRemap] = []
        self.shortcut_remaps: List[ShortcutRemap] = []
        self._original_xmodmap: Optional[str] = None
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                self.key_remaps = [KeyRemap(**r) for r in data.get("key_remaps", [])]
                self.shortcut_remaps = [ShortcutRemap(**r) for r in data.get("shortcut_remaps", [])]
            except (json.JSONDecodeError, TypeError):
                pass

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump({
                "key_remaps": [vars(r) for r in self.key_remaps],
                "shortcut_remaps": [vars(r) for r in self.shortcut_remaps],
            }, f, indent=2)

    def _backup_xmodmap(self):
        try:
            result = subprocess.run(["xmodmap", "-pke"], capture_output=True, text=True, timeout=5)
            self._original_xmodmap = result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def apply_xmodmap_remaps(self) -> Tuple[bool, str]:
        """Apply key remaps via xmodmap."""
        if not self.key_remaps:
            return True, ""
        if self._original_xmodmap is None:
            self._backup_xmodmap()

        lines = []
        for remap in self.key_remaps:
            if not remap.enabled:
                continue
            # Simple key-to-key remap
            lines.append(f"keysym {remap.from_key} = {remap.to_key}")

        if not lines:
            return True, ""

        script = "\n".join(lines)
        try:
            result = subprocess.run(
                ["xmodmap", "-"],
                input=script, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr
        except FileNotFoundError:
            return False, "xmodmap not found. Install x11-xserver-utils."
        except subprocess.TimeoutExpired:
            return False, "xmodmap timed out"

    def reset_to_defaults(self) -> bool:
        """Reset keyboard mappings to system defaults."""
        try:
            subprocess.run(["setxkbmap"], timeout=5)
            if self._original_xmodmap:
                subprocess.run(["xmodmap", "-"], input=self._original_xmodmap,
                               capture_output=True, text=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def generate_keyd_config(self) -> str:
        """Generate a keyd config file for key remapping."""
        lines = ["[ids]", "*", "", "[main]"]
        for remap in self.key_remaps:
            if remap.enabled:
                lines.append(f"{remap.from_key.lower()} = {remap.to_key.lower()}")
        return "\n".join(lines)

    def apply_keyd(self) -> Tuple[bool, str]:
        """Apply remaps using keyd (better alternative to xmodmap)."""
        config = self.generate_keyd_config()
        config_dir = Path("/etc/keyd")
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "powertoys.conf"
            config_file.write_text(config)
            result = subprocess.run(["keyd", "reload"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0, result.stderr
        except PermissionError:
            return False, "Permission denied. Run with sudo to apply keyd config."
        except FileNotFoundError:
            return False, "keyd not found. Install: sudo apt install keyd"
        except subprocess.TimeoutExpired:
            return False, "keyd reload timed out"

    def get_current_keysym(self, keyname: str) -> Optional[str]:
        """Get the current keysym mapping for a key."""
        try:
            result = subprocess.run(["xmodmap", "-pke"], capture_output=True, text=True, timeout=3)
            for line in result.stdout.splitlines():
                if keyname in line:
                    parts = line.split("=")
                    if len(parts) > 1:
                        return parts[1].strip().split()[0]
        except Exception:
            pass
        return None
