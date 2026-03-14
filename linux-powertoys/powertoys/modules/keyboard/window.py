"""Keyboard Manager GTK3 window - full UI for key remapping."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .manager import KeyboardEngine, KeyRemap, ShortcutRemap, XMODMAP_KEY_NAMES

COL_ENABLED = 0
COL_FROM = 1
COL_TO = 2
COL_DESC = 3
COL_IDX = 4


class _KeyPickerDialog(Gtk.Dialog):
    """Dialog that captures a keypress and returns the key name."""

    def __init__(self, parent, title="Press a key"):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(300, 150)
        self._key_name = None

        content = self.get_content_area()
        lbl = Gtk.Label(label="Press any key…")
        lbl.set_margin_top(20)
        content.pack_start(lbl, True, True, 0)

        self._result_lbl = Gtk.Label()
        self._result_lbl.set_markup("<big><b>—</b></big>")
        content.pack_start(self._result_lbl, False, False, 8)

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _on_key(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname:
            self._key_name = keyname
            self._result_lbl.set_markup(f"<big><b>{keyname}</b></big>")
        return True

    def get_key_name(self) -> str:
        return self._key_name or ""


class _RemapDialog(Gtk.Dialog):
    """Dialog for adding/editing a key remap."""

    def __init__(self, parent, remap: KeyRemap = None):
        title = "Edit Key Remap" if remap else "Add Key Remap"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(400, 220)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_border_width(16)
        self.get_content_area().add(grid)

        # From key
        grid.attach(Gtk.Label(label="From key:", xalign=1), 0, 0, 1, 1)
        from_box = Gtk.Box(spacing=4)
        self._from_entry = Gtk.Entry()
        self._from_entry.set_hexpand(True)
        from_box.pack_start(self._from_entry, True, True, 0)
        btn_from = Gtk.Button(label="Capture")
        btn_from.connect("clicked", lambda *a: self._capture("from"))
        from_box.pack_start(btn_from, False, False, 0)
        grid.attach(from_box, 1, 0, 1, 1)

        # To key
        grid.attach(Gtk.Label(label="To key:", xalign=1), 0, 1, 1, 1)
        to_box = Gtk.Box(spacing=4)
        self._to_entry = Gtk.Entry()
        self._to_entry.set_hexpand(True)
        to_box.pack_start(self._to_entry, True, True, 0)
        btn_to = Gtk.Button(label="Capture")
        btn_to.connect("clicked", lambda *a: self._capture("to"))
        to_box.pack_start(btn_to, False, False, 0)
        grid.attach(to_box, 1, 1, 1, 1)

        # Description
        grid.attach(Gtk.Label(label="Description:", xalign=1), 0, 2, 1, 1)
        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("Optional")
        grid.attach(self._desc_entry, 1, 2, 1, 1)

        self._enabled = Gtk.CheckButton(label="Enabled")
        self._enabled.set_active(True)
        grid.attach(self._enabled, 1, 3, 1, 1)

        if remap:
            self._from_entry.set_text(remap.from_key)
            self._to_entry.set_text(remap.to_key)
            self._desc_entry.set_text(remap.description)
            self._enabled.set_active(remap.enabled)

        self.show_all()

    def _capture(self, which: str):
        dlg = _KeyPickerDialog(self, "Press a key to capture")
        if dlg.run() == Gtk.ResponseType.OK:
            key = dlg.get_key_name()
            if which == "from":
                self._from_entry.set_text(key)
            else:
                self._to_entry.set_text(key)
        dlg.destroy()

    def get_remap(self) -> KeyRemap:
        return KeyRemap(
            from_key=self._from_entry.get_text().strip(),
            to_key=self._to_entry.get_text().strip(),
            description=self._desc_entry.get_text().strip(),
            enabled=self._enabled.get_active(),
        )


class KeyboardManagerWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Keyboard Manager")
        self.set_default_size(750, 520)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = KeyboardEngine()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        notebook = Gtk.Notebook()
        vbox.pack_start(notebook, True, True, 0)

        notebook.append_page(self._build_key_remaps_tab(), Gtk.Label(label="Key Remaps"))
        notebook.append_page(self._build_info_tab(), Gtk.Label(label="Current Keyboard Layout"))

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        self._btn_apply = Gtk.Button(label="Apply Remaps")
        self._btn_apply.get_style_context().add_class("suggested-action")
        self._btn_apply.connect("clicked", self._on_apply)
        bar.pack_start(self._btn_apply, False, False, 0)

        btn_reset = Gtk.Button(label="Reset to Defaults")
        btn_reset.connect("clicked", self._on_reset)
        bar.pack_start(btn_reset, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_export = Gtk.Button(label="Export keyd Config")
        btn_export.connect("clicked", self._on_export_keyd)
        bar.pack_start(btn_export, False, False, 0)

        return bar

    def _build_key_remaps_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Info bar
        info = Gtk.InfoBar()
        info.set_message_type(Gtk.MessageType.INFO)
        info.get_content_area().add(Gtk.Label(
            label="Remaps are applied using xmodmap. For system-wide remapping, use keyd (requires root)."
        ))
        box.pack_start(info, False, False, 0)

        # Remap list
        self._store = Gtk.ListStore(bool, str, str, str, int)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)

        # Enabled toggle
        rend_toggle = Gtk.CellRendererToggle()
        rend_toggle.connect("toggled", self._on_toggle_remap)
        col_en = Gtk.TreeViewColumn("On", rend_toggle, active=COL_ENABLED)
        col_en.set_fixed_width(50)
        self._tree.append_column(col_en)

        for title, col_id in [("From Key", COL_FROM), ("To Key", COL_TO), ("Description", COL_DESC)]:
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=col_id)
            col.set_expand(col_id == COL_DESC)
            self._tree.append_column(col)

        self._tree.connect("row-activated", lambda t, p, c: self._on_edit())

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        # Action bar
        action_bar = Gtk.Box(spacing=6)
        action_bar.set_border_width(6)
        btn_add = Gtk.Button(label="+ Add Remap")
        btn_add.connect("clicked", lambda *a: self._on_add())
        action_bar.pack_start(btn_add, False, False, 0)
        btn_edit = Gtk.Button(label="Edit")
        btn_edit.connect("clicked", lambda *a: self._on_edit())
        action_bar.pack_start(btn_edit, False, False, 0)
        btn_del = Gtk.Button(label="Delete")
        btn_del.get_style_context().add_class("destructive-action")
        btn_del.connect("clicked", lambda *a: self._on_delete())
        action_bar.pack_start(btn_del, False, False, 0)
        box.pack_start(action_bar, False, False, 0)

        return box

    def _build_info_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(8)

        box.pack_start(Gtk.Label(label="Current xmodmap output:", xalign=0), False, False, 0)

        self._xmodmap_buf = Gtk.TextBuffer()
        self._xmodmap_view = Gtk.TextView(buffer=self._xmodmap_buf)
        self._xmodmap_view.set_editable(False)
        self._xmodmap_view.override_font(
            __import__("gi.repository.Pango", fromlist=["Pango"]).FontDescription("Monospace 10")
        )

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._xmodmap_view)
        box.pack_start(scroll, True, True, 0)

        btn_refresh = Gtk.Button(label="Refresh")
        btn_refresh.connect("clicked", self._on_refresh_xmodmap)
        box.pack_start(btn_refresh, False, False, 0)

        self._on_refresh_xmodmap(None)
        return box

    def _refresh(self):
        self._store.clear()
        for i, remap in enumerate(self._engine.key_remaps):
            self._store.append([remap.enabled, remap.from_key, remap.to_key, remap.description, i])

    def _on_refresh_xmodmap(self, btn):
        try:
            import subprocess
            result = subprocess.run(["xmodmap", "-pke"], capture_output=True, text=True, timeout=5)
            self._xmodmap_buf.set_text(result.stdout)
        except Exception as e:
            self._xmodmap_buf.set_text(f"xmodmap not available: {e}")

    def _get_selected_index(self) -> int:
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it is None:
            return -1
        return self._store.get_value(it, COL_IDX)

    def _on_toggle_remap(self, renderer, path):
        it = self._store.get_iter(path)
        idx = self._store.get_value(it, COL_IDX)
        self._engine.key_remaps[idx].enabled = not self._engine.key_remaps[idx].enabled
        self._store.set_value(it, COL_ENABLED, self._engine.key_remaps[idx].enabled)
        self._engine.save()

    def _on_add(self):
        dlg = _RemapDialog(self)
        if dlg.run() == Gtk.ResponseType.OK:
            remap = dlg.get_remap()
            if remap.from_key and remap.to_key:
                self._engine.key_remaps.append(remap)
                self._engine.save()
                self._refresh()
        dlg.destroy()

    def _on_edit(self):
        idx = self._get_selected_index()
        if idx < 0:
            return
        dlg = _RemapDialog(self, self._engine.key_remaps[idx])
        if dlg.run() == Gtk.ResponseType.OK:
            self._engine.key_remaps[idx] = dlg.get_remap()
            self._engine.save()
            self._refresh()
        dlg.destroy()

    def _on_delete(self):
        idx = self._get_selected_index()
        if idx >= 0:
            self._engine.key_remaps.pop(idx)
            self._engine.save()
            self._refresh()

    def _on_apply(self, btn):
        ok, err = self._engine.apply_xmodmap_remaps()
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        if ok:
            self._status.push(ctx, "Remaps applied successfully via xmodmap")
        else:
            self._status.push(ctx, f"Failed: {err}")

    def _on_reset(self, btn):
        ok = self._engine.reset_to_defaults()
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, "Reset to defaults" if ok else "Reset failed (xmodmap/setxkbmap not available)")

    def _on_export_keyd(self, btn):
        config = self._engine.generate_keyd_config()
        dialog = Gtk.FileChooserDialog(
            title="Save keyd Config", parent=self, action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("powertoys.conf")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            with open(path, "w") as f:
                f.write(config)
        dialog.destroy()
