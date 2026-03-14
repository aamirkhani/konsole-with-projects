"""Workspaces - save and restore window layout configurations."""
from .engine import WorkspacesEngine, Workspace, WindowState
from .window import WorkspacesWindow

__all__ = ["WorkspacesEngine", "Workspace", "WindowState", "WorkspacesWindow"]
