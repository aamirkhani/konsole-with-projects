"""PowerToys Run engine - application & file search with plugins."""

import os
import re
import subprocess
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Callable


@dataclass
class RunResult:
    title: str
    subtitle: str
    action: Callable
    icon: str = ""       # icon name or path
    score: int = 0
    category: str = "Application"

    def execute(self):
        self.action()


class _ApplicationPlugin:
    """Search .desktop files for applications."""

    def __init__(self):
        self._apps: List[Dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        search_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            str(Path.home() / ".local/share/applications"),
        ]
        for d in search_dirs:
            p = Path(d)
            if not p.is_dir():
                continue
            for desktop in p.glob("*.desktop"):
                info = self._parse_desktop(desktop)
                if info:
                    self._apps.append(info)
        self._loaded = True

    def _parse_desktop(self, path: Path) -> Optional[Dict]:
        try:
            data: Dict = {}
            with open(path, encoding="utf-8", errors="ignore") as f:
                in_entry = False
                for line in f:
                    line = line.strip()
                    if line == "[Desktop Entry]":
                        in_entry = True
                    elif line.startswith("[") and line != "[Desktop Entry]":
                        in_entry = False
                    elif in_entry and "=" in line:
                        key, _, val = line.partition("=")
                        data[key.strip()] = val.strip()

            if data.get("Type") != "Application":
                return None
            if data.get("NoDisplay", "false").lower() == "true":
                return None
            name = data.get("Name")
            if not name:
                return None
            return {
                "name": name,
                "comment": data.get("Comment", ""),
                "exec": data.get("Exec", ""),
                "icon": data.get("Icon", "application-x-executable"),
                "path": str(path),
            }
        except OSError:
            return None

    def search(self, query: str) -> List[RunResult]:
        self._load()
        q = query.lower()
        results = []
        for app in self._apps:
            name = app["name"].lower()
            comment = app["comment"].lower()
            score = 0
            if name == q:
                score = 100
            elif name.startswith(q):
                score = 80
            elif q in name:
                score = 60
            elif q in comment:
                score = 30
            else:
                continue

            exec_cmd = re.sub(r"%[fFuUdDnNickvm]", "", app["exec"]).strip()
            results.append(RunResult(
                title=app["name"],
                subtitle=app["comment"] or app["path"],
                icon=app["icon"],
                score=score,
                category="Application",
                action=lambda cmd=exec_cmd: subprocess.Popen(cmd.split(), start_new_session=True),
            ))
        return results


class _CalculatorPlugin:
    """Evaluate simple math expressions."""

    _SAFE_FNS = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    _SAFE_FNS.update({"abs": abs, "round": round, "min": min, "max": max})

    def search(self, query: str) -> List[RunResult]:
        query = query.strip()
        if not query:
            return []
        try:
            result = eval(query, {"__builtins__": {}}, self._SAFE_FNS)  # nosec
            if isinstance(result, (int, float)):
                val = str(int(result)) if isinstance(result, float) and result.is_integer() else str(result)
                def copy_result(v=val):
                    import subprocess
                    subprocess.run(["xclip", "-selection", "clipboard"], input=v.encode(), capture_output=True)
                return [RunResult(
                    title=f"= {val}",
                    subtitle=f"Calculator: {query}",
                    icon="accessories-calculator",
                    score=95,
                    category="Calculator",
                    action=copy_result,
                )]
        except Exception:
            pass
        return []


class _FileSearchPlugin:
    """Search for files using locate or find."""

    def search(self, query: str) -> List[RunResult]:
        if len(query) < 3:
            return []
        results = []
        try:
            proc = subprocess.run(
                ["locate", "-l", "10", "-i", query],
                capture_output=True, text=True, timeout=3,
            )
            for line in proc.stdout.splitlines()[:10]:
                p = Path(line)
                results.append(RunResult(
                    title=p.name,
                    subtitle=str(p.parent),
                    icon="folder" if p.is_dir() else "text-x-generic",
                    score=50,
                    category="File",
                    action=lambda path=line: subprocess.Popen(["xdg-open", path], start_new_session=True),
                ))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return results


class _SystemCommandPlugin:
    """Built-in system commands."""

    COMMANDS = [
        ("Shutdown", "Power off the computer", "system-shutdown", ["systemctl", "poweroff"]),
        ("Restart", "Restart the computer", "system-restart", ["systemctl", "reboot"]),
        ("Lock Screen", "Lock the session", "system-lock-screen", ["loginctl", "lock-session"]),
        ("Log Out", "End the current session", "system-log-out", ["loginctl", "terminate-session", "self"]),
        ("Sleep", "Suspend to RAM", "system-suspend", ["systemctl", "suspend"]),
        ("Hibernate", "Suspend to disk", "system-hibernate", ["systemctl", "hibernate"]),
    ]

    def search(self, query: str) -> List[RunResult]:
        q = query.lower()
        results = []
        for name, desc, icon, cmd in self.COMMANDS:
            if q in name.lower():
                results.append(RunResult(
                    title=name,
                    subtitle=desc,
                    icon=icon,
                    score=70,
                    category="System",
                    action=lambda c=cmd: subprocess.Popen(c, start_new_session=True),
                ))
        return results


class RunEngine:
    """Main search engine aggregating multiple plugins."""

    def __init__(self):
        self._plugins = [
            _ApplicationPlugin(),
            _CalculatorPlugin(),
            _SystemCommandPlugin(),
            _FileSearchPlugin(),
        ]

    def search(self, query: str, max_results: int = 10) -> List[RunResult]:
        query = query.strip()
        if not query:
            return []

        all_results: List[RunResult] = []
        for plugin in self._plugins:
            try:
                all_results.extend(plugin.search(query))
            except Exception:
                pass

        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:max_results]
