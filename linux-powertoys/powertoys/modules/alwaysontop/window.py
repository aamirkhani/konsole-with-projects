"""AlwaysOnTop GTK3 window."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import threading
from .engine import AlwaysOnTopEngine, ManagedWindow

COL_PINNED = 0
COL_TITLE = 1
COL_PID = 2
COL_WID = 3


class AlwaysOnTopWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Always on Top")
        self.set_default_size(600, 420)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = AlwaysOnTopEngine()
        self._windows: list[ManagedWindow] = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Info banner
        info = Gtk.InfoBar()
        info.set_message_type(Gtk.MessageType.INFO)
        info.get_content_area().add(Gtk.Label(
            label="Pin any window to keep it above all others. Requires wmctrl and an EWMH-compatible compositor."
        ))
        vbox.pack_start(info, False, False, 0)

        # Toolbar
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(8)

        btn_pin_focused = Gtk.Button(label="Pin Focused Window")
        btn_pin_focused.get_style_context().add_class("suggested-action")
        btn_pin_focused.connect("clicked", self._on_pin_focused)
        bar.pack_start(btn_pin_focused, False, False, 0)

        btn_refresh = Gtk.Button(label="Refresh List")
        btn_refresh.connect("clicked", lambda *a: self._refresh())
        bar.pack_start(btn_refresh, False, False, 0)

        btn_unpin_all = Gtk.Button(label="Unpin All")
        btn_unpin_all.connect("clicked", self._on_unpin_all)
        bar.pack_start(btn_unpin_all, False, False, 0)

        vbox.pack_start(bar, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Window list
        self._store = Gtk.ListStore(bool, str, int, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)

        rend_toggle = Gtk.CellRendererToggle()
        rend_toggle.connect("toggled", self._on_toggle)
        col_pin = Gtk.TreeViewColumn("Pinned", rend_toggle, active=COL_PINNED)
        col_pin.set_fixed_width(70)
        self._tree.append_column(col_pin)

        rend_title = Gtk.CellRendererText()
        rend_title.set_property("ellipsize", 3)
        col_title = Gtk.TreeViewColumn("Window Title", rend_title, text=COL_TITLE)
        col_title.set_expand(True)
        col_title.set_sort_column_id(COL_TITLE)
        self._tree.append_column(col_title)

        rend_pid = Gtk.CellRendererText()
        col_pid = Gtk.TreeViewColumn("PID", rend_pid, text=COL_PID)
        col_pid.set_fixed_width(80)
        self._tree.append_column(col_pid)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        vbox.pack_start(scroll, True, True, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)
        self.show_all()

    def _refresh(self):
        self._windows = self._engine.get_windows()
        self._store.clear()
        for w in self._windows:
            self._store.append([w.pinned, w.title, w.pid, w.window_id])
        pinned = self._engine.pinned_count
        self._set_status(f"{len(self._windows)} windows  •  {pinned} pinned")

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _on_toggle(self, renderer, path):
        it = self._store.get_iter(path)
        idx = int(path)
        if 0 <= idx < len(self._windows):
            w = self._windows[idx]
            self._engine.toggle(w)
            self._store.set_value(it, COL_PINNED, w.pinned)
            self._set_status(f"{'Pinned' if w.pinned else 'Unpinned'}: {w.title}")

    def _on_pin_focused(self, btn):
        w = self._engine.pin_focused_window()
        if w:
            self._refresh()
            self._set_status(f"Pinned: {w.title}")
        else:
            self._set_status("Could not detect focused window (xdotool required)")

    def _on_unpin_all(self, btn):
        self._engine.unpin_all()
        self._refresh()
