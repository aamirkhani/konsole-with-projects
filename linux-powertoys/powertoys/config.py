"""Configuration management for Linux PowerToys."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_DIR = Path.home() / ".config" / "linux-powertoys"
CONFIG_FILE = CONFIG_DIR / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    "theme": "system",
    "start_at_login": False,
    "always_run_as_admin": False,
    "modules": {
        "powerrename": {"enabled": True},
        "imageresizer": {"enabled": True, "default_width": 1920, "default_height": 1080, "keep_aspect": True},
        "filelocksmith": {"enabled": True},
        "hostseditor": {"enabled": True},
        "colorpicker": {"enabled": True, "format": "hex", "hotkey": "<ctrl><shift>c"},
        "run": {"enabled": True, "hotkey": "<alt>space", "max_results": 10},
        "fancyzones": {"enabled": True, "layout": "columns", "columns": 2},
        "awake": {"enabled": True},
        "keyboard": {"enabled": True, "remaps": []},
        "screenruler": {"enabled": True, "unit": "pixels"},
        "textextractor": {"enabled": True, "hotkey": "<ctrl><shift>t"},
        "clipboard": {"enabled": True, "max_history": 50},
        "alwaysontop": {"enabled": True},
        "envvars": {"enabled": True},
        "findmymouse": {"enabled": True, "radius": 100, "opacity": 0.7},
        "pasteplain": {"enabled": True, "strip_html": True, "strip_markdown": False},
        "peek": {"enabled": True, "max_preview_kb": 64},
        "shortcutguide": {"enabled": True},
        "videomute": {"enabled": True},
        "workspaces": {"enabled": True},
    },
}


def load() -> Dict[str, Any]:
    """Load configuration, merging with defaults."""
    config = json.loads(json.dumps(_DEFAULTS))  # deep copy
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_cfg = json.load(f)
            _deep_merge(config, user_cfg)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save(config: Dict[str, Any]) -> None:
    """Persist configuration to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get(key: str, default: Any = None) -> Any:
    cfg = load()
    keys = key.split(".")
    val = cfg
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def set(key: str, value: Any) -> None:
    cfg = load()
    keys = key.split(".")
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value
    save(cfg)


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
