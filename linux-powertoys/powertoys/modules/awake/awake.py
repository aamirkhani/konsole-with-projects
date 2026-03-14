"""Awake engine - prevent system sleep and display power-off."""

import subprocess
import threading
import time
from typing import Optional
import os


class AwakeEngine:
    """Keep the system awake using systemd-inhibit, xdotool, or caffeine."""

    def __init__(self):
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._mode = "indefinite"  # "indefinite", "timed", "while_process"
        self._duration_seconds = 3600

    @property
    def active(self) -> bool:
        return self._active

    def start(self, mode: str = "indefinite", duration: int = 3600):
        """Start keeping system awake."""
        if self._active:
            return
        self._mode = mode
        self._duration_seconds = duration
        self._active = True
        self._stop_event.clear()

        # Try systemd-inhibit (best method)
        try:
            cmd = [
                "systemd-inhibit",
                "--what=sleep:idle:handle-lid-switch",
                "--who=Linux PowerToys Awake",
                "--why=User requested",
                "--mode=block",
                "sleep", str(duration) if mode == "timed" else "infinity",
            ]
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if mode == "timed":
                threading.Timer(duration, self.stop).start()
            return
        except FileNotFoundError:
            pass

        # Fallback: xdotool key simulation to prevent screensaver
        self._thread = threading.Thread(target=self._keep_awake_xdotool, daemon=True)
        self._thread.start()

    def _keep_awake_xdotool(self):
        """Periodically simulate a key press to prevent sleep."""
        while not self._stop_event.wait(55):  # every 55 seconds
            try:
                subprocess.run(["xdotool", "key", "shift"], capture_output=True, timeout=3)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # Try xset as fallback
                try:
                    subprocess.run(["xset", "s", "reset"], capture_output=True, timeout=3)
                except Exception:
                    break

    def stop(self):
        """Stop keeping system awake."""
        if not self._active:
            return
        self._active = False
        self._stop_event.set()

        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass
            self._proc = None

    def set_screen_timeout(self, minutes: int):
        """Set display power-off timeout using xset."""
        seconds = minutes * 60
        try:
            subprocess.run(["xset", "dpms", str(seconds), str(seconds), str(seconds)], timeout=3)
            subprocess.run(["xset", "s", str(seconds)], timeout=3)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def disable_screensaver(self, disable: bool = True):
        try:
            if disable:
                subprocess.run(["xset", "s", "off"], timeout=3)
                subprocess.run(["xset", "-dpms"], timeout=3)
            else:
                subprocess.run(["xset", "s", "on"], timeout=3)
                subprocess.run(["xset", "+dpms"], timeout=3)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
