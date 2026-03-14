"""ShortcutGuide engine - collect and display keyboard shortcuts."""

import subprocess
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ShortcutEntry:
    keys: str          # e.g. "Ctrl+C"
    description: str
    context: str = "Global"   # Global | App-specific | Window manager
    category: str = "General"


# Built-in Linux/GNOME/KDE shortcuts
BUILTIN_SHORTCUTS: List[ShortcutEntry] = [
    # Desktop / Window Manager
    ShortcutEntry("Super", "Open application menu / Activities", "Window manager", "Desktop"),
    ShortcutEntry("Super+D", "Show desktop", "Window manager", "Desktop"),
    ShortcutEntry("Super+L", "Lock screen", "Window manager", "Desktop"),
    ShortcutEntry("Super+Tab", "Switch applications", "Window manager", "Desktop"),
    ShortcutEntry("Alt+Tab", "Switch windows", "Window manager", "Desktop"),
    ShortcutEntry("Alt+F4", "Close window", "Window manager", "Desktop"),
    ShortcutEntry("Alt+F2", "Run command dialog", "Window manager", "Desktop"),
    ShortcutEntry("Super+↑", "Maximize window", "Window manager", "Desktop"),
    ShortcutEntry("Super+↓", "Restore / minimize window", "Window manager", "Desktop"),
    ShortcutEntry("Super+←", "Snap window left", "Window manager", "Desktop"),
    ShortcutEntry("Super+→", "Snap window right", "Window manager", "Desktop"),
    ShortcutEntry("Ctrl+Alt+T", "Open terminal", "Window manager", "Desktop"),
    ShortcutEntry("Print", "Take screenshot", "Window manager", "Desktop"),
    ShortcutEntry("Shift+Print", "Take screenshot of area", "Window manager", "Desktop"),
    ShortcutEntry("Ctrl+Print", "Take screenshot of window", "Window manager", "Desktop"),
    # Text editing
    ShortcutEntry("Ctrl+C", "Copy", "Global", "Editing"),
    ShortcutEntry("Ctrl+X", "Cut", "Global", "Editing"),
    ShortcutEntry("Ctrl+V", "Paste", "Global", "Editing"),
    ShortcutEntry("Ctrl+Z", "Undo", "Global", "Editing"),
    ShortcutEntry("Ctrl+Y", "Redo", "Global", "Editing"),
    ShortcutEntry("Ctrl+A", "Select all", "Global", "Editing"),
    ShortcutEntry("Ctrl+F", "Find", "Global", "Editing"),
    ShortcutEntry("Ctrl+H", "Find and replace", "Global", "Editing"),
    ShortcutEntry("Ctrl+S", "Save", "Global", "Editing"),
    ShortcutEntry("Ctrl+Shift+S", "Save as", "Global", "Editing"),
    ShortcutEntry("Ctrl+W", "Close tab / window", "Global", "Editing"),
    ShortcutEntry("Ctrl+T", "New tab", "Global", "Editing"),
    ShortcutEntry("Ctrl+N", "New window", "Global", "Editing"),
    ShortcutEntry("Ctrl+O", "Open file", "Global", "Editing"),
    ShortcutEntry("Ctrl+P", "Print", "Global", "Editing"),
    # Navigation
    ShortcutEntry("Home", "Beginning of line", "Global", "Navigation"),
    ShortcutEntry("End", "End of line", "Global", "Navigation"),
    ShortcutEntry("Ctrl+Home", "Beginning of document", "Global", "Navigation"),
    ShortcutEntry("Ctrl+End", "End of document", "Global", "Navigation"),
    ShortcutEntry("PgUp", "Page up", "Global", "Navigation"),
    ShortcutEntry("PgDn", "Page down", "Global", "Navigation"),
    ShortcutEntry("Ctrl+←", "Previous word", "Global", "Navigation"),
    ShortcutEntry("Ctrl+→", "Next word", "Global", "Navigation"),
    # Terminal
    ShortcutEntry("Ctrl+C", "Interrupt / send SIGINT", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+D", "End of input / logout", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+Z", "Suspend process (SIGTSTP)", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+L", "Clear screen", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+R", "Reverse history search", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+A", "Go to beginning of line", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+E", "Go to end of line", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+U", "Clear line before cursor", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+K", "Clear line after cursor", "Terminal", "Terminal"),
    ShortcutEntry("Ctrl+W", "Delete word before cursor", "Terminal", "Terminal"),
    ShortcutEntry("Tab", "Autocomplete", "Terminal", "Terminal"),
    ShortcutEntry("↑ / ↓", "Navigate command history", "Terminal", "Terminal"),
]


def get_categories() -> List[str]:
    cats = list(dict.fromkeys(s.category for s in BUILTIN_SHORTCUTS))
    return ["All"] + cats


def get_contexts() -> List[str]:
    ctxs = list(dict.fromkeys(s.context for s in BUILTIN_SHORTCUTS))
    return ["All"] + ctxs


class ShortcutGuideEngine:
    def __init__(self):
        self._custom: List[ShortcutEntry] = []

    @property
    def all_shortcuts(self) -> List[ShortcutEntry]:
        return BUILTIN_SHORTCUTS + self._custom

    def search(self, query: str) -> List[ShortcutEntry]:
        q = query.lower()
        return [
            s for s in self.all_shortcuts
            if q in s.keys.lower() or q in s.description.lower() or q in s.category.lower()
        ]

    def filter(self, category: str = "All", context: str = "All") -> List[ShortcutEntry]:
        result = self.all_shortcuts
        if category != "All":
            result = [s for s in result if s.category == category]
        if context != "All":
            result = [s for s in result if s.context == context]
        return result

    def add_custom(self, entry: ShortcutEntry):
        self._custom.append(entry)

    def remove_custom(self, index: int):
        if 0 <= index < len(self._custom):
            self._custom.pop(index)
