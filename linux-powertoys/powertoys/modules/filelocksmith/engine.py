"""FileLocksmith engine - find processes holding file handles on Linux."""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class FileHandle:
    pid: int
    process_name: str
    user: str
    file_path: str
    fd_type: str  # REG, CHR, DIR, FIFO, IPv4, ...
    access: str   # r, w, u (read/write)
    size: int = 0

    @property
    def display_access(self) -> str:
        return {"r": "Read", "w": "Write", "u": "Read/Write", " ": "—"}.get(self.access, self.access)


def _get_username(uid: str) -> str:
    try:
        import pwd
        return pwd.getpwuid(int(uid)).pw_name
    except Exception:
        return uid


def find_handles_lsof(target: str) -> List[FileHandle]:
    """Use lsof to find open file handles matching target path."""
    handles = []
    try:
        result = subprocess.run(
            ["lsof", "-F", "pcntua", target],
            capture_output=True, text=True, timeout=10,
        )
        # Parse lsof field output
        current: dict = {}
        for line in result.stdout.splitlines():
            if not line:
                continue
            key, val = line[0], line[1:]
            if key == "p":  # new process record
                if "pid" in current and "file" in current:
                    handles.append(_make_handle(current))
                current = {"pid": int(val), "files": []}
            elif key == "c":
                current["name"] = val
            elif key == "u":
                current["uid"] = val
            elif key == "f":
                current["fd"] = val
            elif key == "a":
                current["access"] = val
            elif key == "t":
                current["ftype"] = val
            elif key == "n":
                current["file"] = val
                # Emit this file record
                handles.append(FileHandle(
                    pid=current.get("pid", 0),
                    process_name=current.get("name", "?"),
                    user=_get_username(current.get("uid", "?")),
                    file_path=val,
                    fd_type=current.get("ftype", "?"),
                    access=current.get("access", " "),
                ))
        return handles
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def find_handles_proc(target: str) -> List[FileHandle]:
    """Fallback: scan /proc/*/fd symlinks for open handles."""
    handles = []
    target_path = str(Path(target).resolve())

    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        try:
            proc_name = (proc_dir / "comm").read_text().strip()
            status = (proc_dir / "status").read_text()
            uid_match = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
            uid = uid_match.group(1) if uid_match else "?"
            user = _get_username(uid)

            fd_dir = proc_dir / "fd"
            if not fd_dir.exists():
                continue
            for fd in fd_dir.iterdir():
                try:
                    link = os.readlink(fd)
                    if target_path in link or link.startswith(target_path):
                        handles.append(FileHandle(
                            pid=pid,
                            process_name=proc_name,
                            user=user,
                            file_path=link,
                            fd_type="REG",
                            access="u",
                        ))
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue

    return handles


class FileLocksmithEngine:
    """Find which processes have a file or directory open."""

    def find(self, path: str) -> List[FileHandle]:
        """Return all processes with handles on path (file or dir)."""
        # Try lsof first (most complete), then fall back to /proc
        handles = find_handles_lsof(path)
        if not handles:
            handles = find_handles_proc(path)

        # Deduplicate
        seen: Set[tuple] = set()
        unique = []
        for h in handles:
            key = (h.pid, h.file_path)
            if key not in seen:
                seen.add(key)
                unique.append(h)
        return unique

    def kill_process(self, pid: int, force: bool = False) -> bool:
        """Send SIGTERM (or SIGKILL if force) to a process."""
        import signal
        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def get_open_files(self, pid: int) -> List[str]:
        """Return all files open by a specific PID."""
        fd_dir = Path(f"/proc/{pid}/fd")
        files = []
        try:
            for fd in fd_dir.iterdir():
                try:
                    files.append(os.readlink(fd))
                except OSError:
                    pass
        except (OSError, PermissionError):
            pass
        return sorted(set(files))
