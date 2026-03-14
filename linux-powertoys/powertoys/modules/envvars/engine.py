"""Environment Variables engine - read, edit and persist env vars."""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class EnvVar:
    name: str
    value: str
    source: str = "session"   # session | profile | system
    enabled: bool = True
    original_value: Optional[str] = None

    @property
    def modified(self) -> bool:
        return self.original_value is not None and self.value != self.original_value

    def validate(self) -> Optional[str]:
        if not self.name:
            return "Variable name cannot be empty"
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", self.name):
            return f"Invalid name '{self.name}': must start with letter/underscore, alphanumeric only"
        return None

    @property
    def is_path_var(self) -> bool:
        return "PATH" in self.name.upper()


# Files we read/write for persistent env vars
PROFILE_FILES = [
    Path.home() / ".profile",
    Path.home() / ".bashrc",
    Path.home() / ".bash_profile",
    Path.home() / ".zshrc",
    Path.home() / ".config" / "environment.d" / "powertoys.conf",
]

SYSTEM_ENV_FILES = [
    Path("/etc/environment"),
    Path("/etc/profile.d/powertoys.sh"),
]

# Marker for variables managed by PowerToys
_PT_MARKER = "# Linux PowerToys managed"


class EnvVarsEngine:
    def __init__(self):
        self._session_vars: Dict[str, EnvVar] = {}
        self._profile_vars: Dict[str, EnvVar] = {}
        self._system_vars: Dict[str, EnvVar] = {}
        self.load()

    def load(self):
        """Load current session variables + discover profile/system vars."""
        # Session: current os.environ
        for name, value in sorted(os.environ.items()):
            self._session_vars[name] = EnvVar(
                name=name, value=value, source="session",
                original_value=value,
            )

        # Profile: parse ~/.profile and ~/.bashrc for export statements
        for profile_file in PROFILE_FILES[:3]:  # only user-writable ones
            if profile_file.exists():
                for name, value in self._parse_shell_exports(profile_file):
                    if name not in self._profile_vars:
                        self._profile_vars[name] = EnvVar(
                            name=name, value=value, source="profile",
                            original_value=value,
                        )

        # System: /etc/environment
        if SYSTEM_ENV_FILES[0].exists():
            for name, value in self._parse_etc_environment(SYSTEM_ENV_FILES[0]):
                self._system_vars[name] = EnvVar(
                    name=name, value=value, source="system",
                    original_value=value,
                )

    def _parse_shell_exports(self, path: Path) -> List[Tuple[str, str]]:
        results = []
        try:
            content = path.read_text()
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'^export\s+([A-Za-z_][A-Za-z0-9_]*)=["\'"]?(.+?)["\'"]?\s*(?:#.*)?$', line)
                if m:
                    results.append((m.group(1), m.group(2).strip('"\'').strip()))
        except OSError:
            pass
        return results

    def _parse_etc_environment(self, path: Path) -> List[Tuple[str, str]]:
        results = []
        try:
            content = path.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=["\'"]?(.+?)["\'"]?\s*$', line)
                if m:
                    results.append((m.group(1), m.group(2)))
        except OSError:
            pass
        return results

    def get_all(self, source: str = "all") -> List[EnvVar]:
        if source == "session":
            return list(self._session_vars.values())
        if source == "profile":
            return list(self._profile_vars.values())
        if source == "system":
            return list(self._system_vars.values())
        # Merge: session is authoritative
        merged: Dict[str, EnvVar] = {}
        for d in [self._system_vars, self._profile_vars, self._session_vars]:
            merged.update({v.name: v for v in d.values()})
        return sorted(merged.values(), key=lambda v: v.name)

    def search(self, query: str) -> List[EnvVar]:
        q = query.lower()
        return [v for v in self.get_all() if q in v.name.lower() or q in v.value.lower()]

    def set_session(self, name: str, value: str):
        """Set variable for current session only (affects os.environ)."""
        os.environ[name] = value
        self._session_vars[name] = EnvVar(name=name, value=value, source="session")

    def delete_session(self, name: str):
        os.environ.pop(name, None)
        self._session_vars.pop(name, None)

    def save_to_profile(self, var: EnvVar, profile_file: Path = None) -> Optional[str]:
        """Persist a variable to user profile file."""
        target = profile_file or (Path.home() / ".profile")
        try:
            content = target.read_text() if target.exists() else ""
            lines = content.splitlines()

            # Remove existing export for this var
            lines = [l for l in lines if not re.match(rf"^export\s+{re.escape(var.name)}=", l)]

            # Append new export
            if var.enabled:
                lines.append(f'export {var.name}="{var.value}"  {_PT_MARKER}')

            target.write_text("\n".join(lines) + "\n")
            self._profile_vars[var.name] = var
            return None
        except OSError as e:
            return str(e)

    def save_to_system(self, var: EnvVar) -> Optional[str]:
        """Write to /etc/environment (requires root)."""
        target = SYSTEM_ENV_FILES[0]
        try:
            content = target.read_text() if target.exists() else ""
            lines = content.splitlines()
            lines = [l for l in lines if not re.match(rf"^{re.escape(var.name)}=", l)]
            if var.enabled:
                lines.append(f'{var.name}="{var.value}"')
            target.write_text("\n".join(lines) + "\n")
            self._system_vars[var.name] = var
            return None
        except PermissionError:
            return "Permission denied. Run PowerToys with sudo to edit system variables."
        except OSError as e:
            return str(e)

    def export_as_shell(self, vars_list: List[EnvVar]) -> str:
        """Generate shell script snippet for given variables."""
        lines = ["#!/usr/bin/env bash", "# Generated by Linux PowerToys Environment Variables", ""]
        for v in vars_list:
            lines.append(f'export {v.name}="{v.value}"')
        return "\n".join(lines)

    def get_path_entries(self) -> List[str]:
        """Return PATH entries as a list."""
        return os.environ.get("PATH", "").split(":")

    def set_path_entries(self, entries: List[str]):
        """Set PATH from a list of directories."""
        os.environ["PATH"] = ":".join(e for e in entries if e)
        if "PATH" in self._session_vars:
            self._session_vars["PATH"].value = os.environ["PATH"]
