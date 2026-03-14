"""ClipboardHistory engine - monitor and manage clipboard history."""

import threading
import time
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable
from datetime import datetime


@dataclass
class ClipboardEntry:
    content: str
    timestamp: float = field(default_factory=time.time)
    content_type: str = "text"  # text, image_path
    pinned: bool = False
    label: str = ""

    @property
    def preview(self) -> str:
        lines = self.content.splitlines()
        first = lines[0] if lines else ""
        if len(first) > 80:
            first = first[:77] + "…"
        if len(lines) > 1:
            first += f" [{len(lines)} lines]"
        return first

    @property
    def timestamp_str(self) -> str:
        dt = datetime.fromtimestamp(self.timestamp)
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")

    @property
    def size_str(self) -> str:
        n = len(self.content)
        if n < 1024:
            return f"{n} chars"
        return f"{n / 1024:.1f} KB"


HISTORY_FILE = Path.home() / ".config" / "linux-powertoys" / "clipboard_history.json"


class ClipboardEngine:
    """Clipboard monitor using GTK or xclip polling."""

    def __init__(self, max_items: int = 50):
        self.max_items = max_items
        self.history: List[ClipboardEntry] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_content = ""
        self._callbacks: List[Callable] = []
        self.load_history()

    def on_change(self, callback: Callable):
        """Register a callback for new clipboard content."""
        self._callbacks.append(callback)

    def start_monitoring(self):
        """Start clipboard monitoring in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        self._running = False

    def _monitor_loop(self):
        """Poll clipboard every 500ms for changes."""
        while self._running:
            try:
                content = self._read_clipboard()
                if content and content != self._last_content:
                    self._last_content = content
                    self._add_entry(content)
            except Exception:
                pass
            time.sleep(0.5)

    def _read_clipboard(self) -> Optional[str]:
        import subprocess
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            result = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _add_entry(self, content: str):
        # Don't duplicate consecutive entries
        if self.history and self.history[0].content == content:
            return
        # Don't add entries that are in pinned list already
        for entry in self.history:
            if entry.content == content and not entry.pinned:
                self.history.remove(entry)
                break

        entry = ClipboardEntry(content=content)
        self.history.insert(0, entry)

        # Trim unpinned entries
        unpinned = [e for e in self.history if not e.pinned]
        if len(unpinned) > self.max_items:
            oldest = unpinned[-1]
            self.history.remove(oldest)

        for cb in self._callbacks:
            cb(entry)

        self.save_history()

    def set_clipboard(self, content: str):
        """Write text to the system clipboard."""
        import subprocess
        self._last_content = content  # prevent re-adding
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=content.encode(), timeout=3,
            )
            return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=content.encode(), timeout=3,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def delete_entry(self, entry: ClipboardEntry):
        if entry in self.history:
            self.history.remove(entry)
            self.save_history()

    def pin_entry(self, entry: ClipboardEntry, pinned: bool = True):
        entry.pinned = pinned
        self.save_history()

    def clear_history(self, keep_pinned: bool = True):
        if keep_pinned:
            self.history = [e for e in self.history if e.pinned]
        else:
            self.history.clear()
        self.save_history()

    def search(self, query: str) -> List[ClipboardEntry]:
        q = query.lower()
        return [e for e in self.history if q in e.content.lower() or q in e.label.lower()]

    def save_history(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "content": e.content[:10000],  # cap at 10KB per entry
                "timestamp": e.timestamp,
                "content_type": e.content_type,
                "pinned": e.pinned,
                "label": e.label,
            }
            for e in self.history
        ]
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE) as f:
                    data = json.load(f)
                self.history = [ClipboardEntry(**d) for d in data]
            except Exception:
                self.history = []
