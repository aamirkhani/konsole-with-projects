"""VideoConferenceMute engine - toggle mic/camera for video calls."""

import subprocess
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class AudioDevice:
    index: int
    name: str
    is_muted: bool


def _pactl(args: List[str]) -> Optional[str]:
    try:
        r = subprocess.run(
            ["pactl"] + args, capture_output=True, text=True, timeout=5
        )
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _amixer(args: List[str]) -> Optional[str]:
    try:
        r = subprocess.run(
            ["amixer"] + args, capture_output=True, text=True, timeout=5
        )
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def list_microphones() -> List[AudioDevice]:
    """List available microphone (source) devices via pactl."""
    out = _pactl(["list", "sources", "short"])
    if out is None:
        return []
    devices = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                idx = int(parts[0])
                name = parts[1]
                # Skip monitor sources
                if "monitor" not in name.lower():
                    muted = _is_source_muted(idx)
                    devices.append(AudioDevice(index=idx, name=name, is_muted=muted))
            except (ValueError, IndexError):
                continue
    return devices


def _is_source_muted(index: int) -> bool:
    out = _pactl(["list", "sources"])
    if not out:
        return False
    # Find the source block for this index and check Mute field
    in_block = False
    for line in out.splitlines():
        if f"Source #{index}" in line:
            in_block = True
        if in_block and "Mute:" in line:
            return "yes" in line.lower()
        if in_block and line.strip() == "" and "Mute:" not in line:
            # May have passed this source's block
            pass
    return False


def set_microphone_mute(index: int, mute: bool) -> bool:
    """Mute or unmute a source (microphone) by index."""
    val = "1" if mute else "0"
    out = _pactl(["set-source-mute", str(index), val])
    return out is not None


def toggle_microphone_mute(index: int) -> bool:
    """Toggle mute state of a microphone."""
    out = _pactl(["set-source-mute", str(index), "toggle"])
    return out is not None


def list_cameras() -> List[str]:
    """List /dev/video* camera devices."""
    import glob
    devices = sorted(glob.glob("/dev/video*"))
    return devices


def is_camera_active(device: str) -> bool:
    """Check if a camera device is currently in use (opened by a process)."""
    try:
        r = subprocess.run(
            ["fuser", device], capture_output=True, text=True, timeout=3
        )
        return bool(r.stdout.strip())
    except FileNotFoundError:
        pass
    # Fallback: check /proc/*/fd
    import os
    import glob as g
    try:
        for fd_path in g.glob("/proc/*/fd/*"):
            try:
                if os.readlink(fd_path) == device:
                    return True
            except OSError:
                continue
    except Exception:
        pass
    return False


def block_camera(device: str) -> Tuple[bool, str]:
    """Attempt to block camera by changing permissions (requires root or udev)."""
    try:
        r = subprocess.run(
            ["chmod", "000", device],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            return True, ""
        return False, r.stderr.strip()
    except Exception as e:
        return False, str(e)


def unblock_camera(device: str) -> Tuple[bool, str]:
    """Restore camera permissions."""
    try:
        r = subprocess.run(
            ["chmod", "660", device],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            return True, ""
        return False, r.stderr.strip()
    except Exception as e:
        return False, str(e)


class VideoMuteEngine:
    def __init__(self):
        self._mic_muted: bool = False
        self._cam_blocked: bool = False
        self._selected_mic_index: Optional[int] = None

    @property
    def mic_muted(self) -> bool:
        return self._mic_muted

    @property
    def cam_blocked(self) -> bool:
        return self._cam_blocked

    def get_microphones(self) -> List[AudioDevice]:
        return list_microphones()

    def get_cameras(self) -> List[str]:
        return list_cameras()

    def select_microphone(self, index: int):
        self._selected_mic_index = index

    def toggle_mic(self) -> Tuple[bool, str]:
        """Toggle mute for selected microphone. Returns (success, message)."""
        mics = list_microphones()
        if not mics:
            # Try amixer fallback
            out = _amixer(["sset", "Capture", "toggle"])
            if out:
                self._mic_muted = not self._mic_muted
                return True, "Toggled via amixer"
            return False, "No microphone found (pactl/amixer required)"

        idx = self._selected_mic_index if self._selected_mic_index is not None else mics[0].index
        ok = toggle_microphone_mute(idx)
        if ok:
            self._mic_muted = not self._mic_muted
            state = "Muted" if self._mic_muted else "Unmuted"
            return True, f"Microphone {state}"
        return False, "Failed to toggle microphone"

    def set_mic_mute(self, mute: bool) -> Tuple[bool, str]:
        mics = list_microphones()
        if not mics:
            return False, "No microphone found"
        idx = self._selected_mic_index if self._selected_mic_index is not None else mics[0].index
        ok = set_microphone_mute(idx, mute)
        if ok:
            self._mic_muted = mute
            return True, "Microphone muted" if mute else "Microphone unmuted"
        return False, "Failed"

    def toggle_camera(self, device: str) -> Tuple[bool, str]:
        """Toggle camera block (requires root for chmod)."""
        if self._cam_blocked:
            ok, err = unblock_camera(device)
            if ok:
                self._cam_blocked = False
                return True, "Camera unblocked"
            return False, f"Cannot unblock camera: {err}"
        else:
            ok, err = block_camera(device)
            if ok:
                self._cam_blocked = True
                return True, "Camera blocked"
            return False, f"Cannot block camera (run as root): {err}"

    def get_active_cameras(self) -> List[str]:
        return [d for d in list_cameras() if is_camera_active(d)]
