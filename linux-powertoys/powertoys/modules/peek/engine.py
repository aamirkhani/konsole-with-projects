"""Peek engine - quick file preview with format detection."""

import os
import mimetypes
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class FileInfo:
    path: Path
    name: str
    size: int
    mime_type: str
    category: str    # text | image | pdf | archive | video | audio | binary
    size_str: str


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def classify_file(path: Path) -> FileInfo:
    """Determine file category and metadata."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "application/octet-stream"

    size = path.stat().st_size if path.exists() else 0

    if mime.startswith("text/") or mime in (
        "application/json", "application/xml", "application/javascript",
        "application/x-sh", "application/x-yaml",
    ):
        category = "text"
    elif mime.startswith("image/"):
        category = "image"
    elif mime == "application/pdf":
        category = "pdf"
    elif mime.startswith("video/"):
        category = "video"
    elif mime.startswith("audio/"):
        category = "audio"
    elif mime in (
        "application/zip", "application/x-tar", "application/gzip",
        "application/x-bzip2", "application/x-xz", "application/x-7z-compressed",
        "application/x-rar",
    ):
        category = "archive"
    else:
        # Try to detect text files by reading first bytes
        try:
            with open(path, "rb") as f:
                chunk = f.read(512)
            if b"\x00" not in chunk:
                category = "text"
            else:
                category = "binary"
        except OSError:
            category = "binary"

    return FileInfo(
        path=path,
        name=path.name,
        size=size,
        mime_type=mime,
        category=category,
        size_str=_human_size(size),
    )


def read_text_preview(path: Path, max_chars: int = 8192) -> str:
    """Read text content for preview."""
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(max_chars)
    except OSError as e:
        return f"Error reading file: {e}"


def list_archive_contents(path: Path) -> str:
    """List archive contents using system tools."""
    suffix = path.suffix.lower()
    cmds = {
        ".zip": ["unzip", "-l", str(path)],
        ".tar": ["tar", "-tvf", str(path)],
        ".gz": ["tar", "-tzvf", str(path)],
        ".bz2": ["tar", "-tjvf", str(path)],
        ".xz": ["tar", "-tJvf", str(path)],
        ".7z": ["7z", "l", str(path)],
    }
    cmd = cmds.get(suffix)
    if not cmd:
        # Try tar as fallback
        cmd = ["tar", "-tvf", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout if r.returncode == 0 else r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"Cannot list archive: {e}"


class PeekEngine:
    def __init__(self):
        self.font_name: str = "Monospace 10"
        self.wrap_text: bool = True
        self.syntax_highlight: bool = True
        self.max_preview_bytes: int = 1024 * 64  # 64 KB

    def get_file_info(self, path: Path) -> FileInfo:
        return classify_file(path)

    def get_text_content(self, path: Path) -> str:
        return read_text_preview(path, self.max_preview_bytes)

    def get_archive_listing(self, path: Path) -> str:
        return list_archive_contents(path)

    def open_with_default(self, path: Path) -> bool:
        """Open file with system default application."""
        try:
            subprocess.Popen(["xdg-open", str(path)])
            return True
        except FileNotFoundError:
            return False
