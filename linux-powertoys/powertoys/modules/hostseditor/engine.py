"""HostsEditor engine - parse, edit and write /etc/hosts entries."""

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


HOSTS_FILE = "/etc/hosts"

_IP_RE = re.compile(
    r"^((\d{1,3}\.){3}\d{1,3}|"       # IPv4
    r"([0-9a-fA-F:]+))$"               # IPv6
)


@dataclass
class HostsEntry:
    ip: str
    hostnames: List[str]
    comment: str = ""
    enabled: bool = True
    line_num: int = -1

    @property
    def primary_hostname(self) -> str:
        return self.hostnames[0] if self.hostnames else ""

    def to_line(self) -> str:
        prefix = "" if self.enabled else "# "
        line = f"{prefix}{self.ip}\t{' '.join(self.hostnames)}"
        if self.comment:
            line += f"  # {self.comment}"
        return line

    def valid_ip(self) -> bool:
        return bool(_IP_RE.match(self.ip))


def parse_hosts_file(path: str = HOSTS_FILE) -> Tuple[List[HostsEntry], List[str]]:
    """
    Parse a hosts file into HostsEntry objects and raw comment lines.
    Returns (entries, raw_lines) where raw_lines holds comment-only lines.
    """
    entries: List[HostsEntry] = []
    raw_lines: List[str] = []

    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return [], []

    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        original = stripped
        enabled = True

        # Disabled entry starts with #
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            parts = candidate.split()
            if parts and _IP_RE.match(parts[0]) and len(parts) >= 2:
                enabled = False
                stripped = candidate
            else:
                raw_lines.append(original)
                continue

        if not stripped.strip():
            raw_lines.append(original)
            continue

        # Strip inline comment
        comment = ""
        if " #" in stripped:
            idx = stripped.index(" #")
            comment = stripped[idx + 2:].strip()
            stripped = stripped[:idx].strip()
        elif "\t#" in stripped:
            idx = stripped.index("\t#")
            comment = stripped[idx + 2:].strip()
            stripped = stripped[:idx].strip()

        parts = stripped.split()
        if len(parts) >= 2:
            ip = parts[0]
            hostnames = parts[1:]
            entries.append(HostsEntry(ip=ip, hostnames=hostnames, comment=comment, enabled=enabled, line_num=i))

    return entries, raw_lines


class HostsEngine:
    def __init__(self, hosts_path: str = HOSTS_FILE):
        self.hosts_path = hosts_path
        self.entries: List[HostsEntry] = []
        self._header_lines: List[str] = []
        self.load()

    def load(self):
        self.entries, _ = parse_hosts_file(self.hosts_path)
        # Preserve header comments
        self._header_lines = []
        try:
            with open(self.hosts_path) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#") or not stripped:
                        self._header_lines.append(line.rstrip("\n"))
                    else:
                        break
        except OSError:
            pass

    def save(self) -> Optional[str]:
        """Write entries to hosts file. Returns error string or None on success."""
        lines = []
        # Keep header comments
        if self._header_lines:
            lines.extend(self._header_lines)
            lines.append("")

        for entry in self.entries:
            lines.append(entry.to_line())

        content = "\n".join(lines) + "\n"

        # Write to temp then atomic rename (requires root for /etc/hosts)
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", delete=False,
                dir=os.path.dirname(self.hosts_path),
                prefix=".hosts_tmp_",
            )
            tmp.write(content)
            tmp.close()
            # Preserve permissions
            stat = os.stat(self.hosts_path)
            os.chmod(tmp.name, stat.st_mode)
            shutil.move(tmp.name, self.hosts_path)
            return None
        except OSError as e:
            return str(e)

    def add_entry(self, ip: str, hostnames: List[str], comment: str = "", enabled: bool = True):
        self.entries.append(HostsEntry(ip=ip, hostnames=hostnames, comment=comment, enabled=enabled))

    def remove_entry(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries.pop(index)

    def toggle_entry(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries[index].enabled = not self.entries[index].enabled

    def find(self, query: str) -> List[int]:
        """Return indices of entries matching query (IP or hostname)."""
        query = query.lower()
        results = []
        for i, entry in enumerate(self.entries):
            if query in entry.ip.lower() or any(query in h.lower() for h in entry.hostnames):
                results.append(i)
        return results

    def validate_entry(self, entry: HostsEntry) -> Optional[str]:
        if not entry.ip:
            return "IP address is required"
        if not entry.valid_ip():
            return f"Invalid IP address: {entry.ip}"
        if not entry.hostnames:
            return "At least one hostname is required"
        return None
