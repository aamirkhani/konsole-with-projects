"""HostsEditor GTK3 window - full /etc/hosts manager UI."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from .engine import HostsEngine, HostsEntry

COL_ENABLED = 0
COL_IP = 1
COL_HOSTNAMES = 2
COL_COMMENT = 3
COL_INDEX = 4


class _EntryDialog(Gtk.Dialog):
    """Dialog for adding / editing a hosts entry."""

    def __init__(self, parent, entry: HostsEntry = None):
        title = "Edit Entry" if entry else "Add Entry"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(420, 220)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_border_width(16)
        self.get_content_area().add(grid)

        grid.attach(Gtk.Label(label="IP Address:", xalign=1), 0, 0, 1, 1)
        self.ip_entry = Gtk.Entry()
        self.ip_entry.set_placeholder_text("e.g. 127.0.0.1")
        grid.attach(self.ip_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Hostnames:", xalign=1), 0, 1, 1, 1)
        self.hosts_entry = Gtk.Entry()
        self.hosts_entry.set_placeholder_text("space-separated, e.g. example.com www.example.com")
        self.hosts_entry.set_hexpand(True)
        grid.attach(self.hosts_entry, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Comment:", xalign=1), 0, 2, 1, 1)
        self.comment_entry = Gtk.Entry()
        self.comment_entry.set_placeholder_text("Optional")
        grid.attach(self.comment_entry, 1, 2, 1, 1)

        self.enabled_check = Gtk.CheckButton(label="Enabled")
        self.enabled_check.set_active(True)
        grid.attach(self.enabled_check, 1, 3, 1, 1)

        self._error_label = Gtk.Label(xalign=0)
        self._error_label.get_style_context().add_class("error")
        grid.attach(self._error_label, 0, 4, 2, 1)

        if entry:
            self.ip_entry.set_text(entry.ip)
            self.hosts_entry.set_text(" ".join(entry.hostnames))
            self.comment_entry.set_text(entry.comment)
            self.enabled_check.set_active(entry.enabled)

        self.show_all()

    def get_entry(self) -> HostsEntry:
        return HostsEntry(
            ip=self.ip_entry.get_text().strip(),
            hostnames=self.hosts_entry.get_text().split(),
            comment=self.comment_entry.get_text().strip(),
            enabled=self.enabled_check.get_active(),
        )

    def show_error(self, msg: str):
        self._error_label.set_markup(f"<span foreground='red'>{msg}</span>")


class HostsEditorWindow(Gtk.Window):
    def __init__(self, hosts_path: str = "/etc/hosts", parent=None):
        super().__init__(title="Hosts File Editor")
        self.set_default_size(850, 550)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = HostsEngine(hosts_path)
        self._modified = False

        self._build_ui()
        self._refresh_list()

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        vbox.pack_start(self._build_search(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        vbox.pack_start(self._build_list(), True, True, 0)
        vbox.pack_start(self._build_editor_bar(), False, False, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()
        self.connect("delete-event", self._on_close)

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        self._btn_save = Gtk.Button(label="Save")
        self._btn_save.get_style_context().add_class("suggested-action")
        self._btn_save.connect("clicked", self._on_save)
        bar.pack_start(self._btn_save, False, False, 0)

        self._btn_reload = Gtk.Button(label="Reload")
        self._btn_reload.connect("clicked", lambda *a: self._reload())
        bar.pack_start(self._btn_reload, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_backup = Gtk.Button(label="Backup")
        btn_backup.connect("clicked", self._on_backup)
        bar.pack_start(btn_backup, False, False, 0)

        btn_restore = Gtk.Button(label="Restore Backup")
        btn_restore.connect("clicked", self._on_restore)
        bar.pack_start(btn_restore, False, False, 0)

        # Hosts path label
        self._path_lbl = Gtk.Label(xalign=0)
        self._path_lbl.set_markup(f"<small>Editing: <b>{self._engine.hosts_path}</b></small>")
        bar.pack_end(self._path_lbl, False, False, 8)

        return bar

    def _build_search(self):
        box = Gtk.Box(spacing=6)
        box.set_border_width(6)
        box.pack_start(Gtk.Label(label="Search:"), False, False, 0)
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text("Filter by IP or hostname…")
        self._search.connect("search-changed", lambda *a: self._filter.refilter())
        box.pack_start(self._search, True, True, 0)
        return box

    def _build_list(self):
        # enabled, ip, hostnames, comment, index
        self._store = Gtk.ListStore(bool, str, str, str, int)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._row_visible)

        self._tree = Gtk.TreeView(model=self._filter)
        self._tree.set_headers_clickable(True)
        self._tree.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

        # Enabled toggle
        rend_toggle = Gtk.CellRendererToggle()
        rend_toggle.connect("toggled", self._on_toggle_enabled)
        col_en = Gtk.TreeViewColumn("On", rend_toggle, active=COL_ENABLED)
        col_en.set_fixed_width(50)
        self._tree.append_column(col_en)

        for title, col_id, expand in [
            ("IP Address", COL_IP, False),
            ("Hostnames", COL_HOSTNAMES, True),
            ("Comment", COL_COMMENT, False),
        ]:
            rend = Gtk.CellRendererText()
            rend.set_property("editable", False)
            if col_id == COL_HOSTNAMES:
                rend.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, rend, text=col_id)
            col.set_resizable(True)
            col.set_expand(expand)
            self._tree.append_column(col)

        self._tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self._tree.connect("row-activated", self._on_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        return scroll

    def _build_editor_bar(self):
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(6)

        self._btn_add = Gtk.Button(label="+ Add Entry")
        self._btn_add.connect("clicked", self._on_add)
        bar.pack_start(self._btn_add, False, False, 0)

        self._btn_edit = Gtk.Button(label="Edit")
        self._btn_edit.connect("clicked", self._on_edit)
        bar.pack_start(self._btn_edit, False, False, 0)

        self._btn_del = Gtk.Button(label="Delete")
        self._btn_del.get_style_context().add_class("destructive-action")
        self._btn_del.connect("clicked", self._on_delete)
        bar.pack_start(self._btn_del, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self._btn_toggle = Gtk.Button(label="Enable/Disable")
        self._btn_toggle.connect("clicked", self._on_toggle_selected)
        bar.pack_start(self._btn_toggle, False, False, 0)

        return bar

    # ── Logic ──────────────────────────────────────────────────────────────

    def _row_visible(self, model, it, data):
        q = self._search.get_text().lower() if hasattr(self, "_search") else ""
        if not q:
            return True
        ip = model.get_value(it, COL_IP).lower()
        hosts = model.get_value(it, COL_HOSTNAMES).lower()
        return q in ip or q in hosts

    def _refresh_list(self):
        self._store.clear()
        for i, entry in enumerate(self._engine.entries):
            self._store.append([
                entry.enabled,
                entry.ip,
                " ".join(entry.hostnames),
                entry.comment,
                i,
            ])
        n = len(self._engine.entries)
        self._set_status(f"{n} entr{'y' if n == 1 else 'ies'}")

    def _reload(self):
        if self._modified:
            dlg = Gtk.MessageDialog(
                parent=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Discard unsaved changes and reload?",
            )
            resp = dlg.run()
            dlg.destroy()
            if resp != Gtk.ResponseType.YES:
                return
        self._engine.load()
        self._modified = False
        self._refresh_list()

    def _mark_modified(self):
        self._modified = True
        self.set_title("Hosts File Editor *")

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _get_selected_index(self) -> int:
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it is None:
            return -1
        child_it = model.convert_iter_to_child_iter(it)
        return self._store.get_value(child_it, COL_INDEX)

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_toggle_enabled(self, renderer, path):
        it = self._filter.get_iter(path)
        child_it = self._filter.convert_iter_to_child_iter(it)
        idx = self._store.get_value(child_it, COL_INDEX)
        self._engine.toggle_entry(idx)
        self._store.set_value(child_it, COL_ENABLED, self._engine.entries[idx].enabled)
        self._mark_modified()

    def _on_row_activated(self, tree, path, col):
        self._on_edit(None)

    def _on_add(self, btn):
        dlg = _EntryDialog(self)
        while True:
            resp = dlg.run()
            if resp != Gtk.ResponseType.OK:
                break
            entry = dlg.get_entry()
            err = self._engine.validate_entry(entry)
            if err:
                dlg.show_error(err)
                continue
            self._engine.add_entry(entry.ip, entry.hostnames, entry.comment, entry.enabled)
            self._refresh_list()
            self._mark_modified()
            break
        dlg.destroy()

    def _on_edit(self, btn):
        idx = self._get_selected_index()
        if idx < 0:
            return
        entry = self._engine.entries[idx]
        dlg = _EntryDialog(self, entry)
        while True:
            resp = dlg.run()
            if resp != Gtk.ResponseType.OK:
                break
            new_entry = dlg.get_entry()
            err = self._engine.validate_entry(new_entry)
            if err:
                dlg.show_error(err)
                continue
            self._engine.entries[idx] = new_entry
            self._refresh_list()
            self._mark_modified()
            break
        dlg.destroy()

    def _on_delete(self, btn):
        idx = self._get_selected_index()
        if idx < 0:
            return
        entry = self._engine.entries[idx]
        msg = Gtk.MessageDialog(
            parent=self, flags=0, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete entry for {entry.ip}?",
        )
        if msg.run() == Gtk.ResponseType.YES:
            self._engine.remove_entry(idx)
            self._refresh_list()
            self._mark_modified()
        msg.destroy()

    def _on_toggle_selected(self, btn):
        idx = self._get_selected_index()
        if idx >= 0:
            self._engine.toggle_entry(idx)
            self._refresh_list()
            self._mark_modified()

    def _on_save(self, btn):
        err = self._engine.save()
        if err:
            msg = Gtk.MessageDialog(
                parent=self, flags=0, message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"Failed to save: {err}",
            )
            msg.format_secondary_text("You may need to run this tool with administrator privileges (sudo).")
            msg.run()
            msg.destroy()
        else:
            self._modified = False
            self.set_title("Hosts File Editor")
            self._set_status("Saved successfully")

    def _on_backup(self, btn):
        import shutil, datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = f"{self._engine.hosts_path}.backup_{ts}"
        try:
            shutil.copy2(self._engine.hosts_path, dest)
            self._set_status(f"Backup saved: {dest}")
        except OSError as e:
            self._set_status(f"Backup failed: {e}")

    def _on_restore(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Select Backup File", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            backup = dialog.get_filename()
            import shutil
            try:
                shutil.copy2(backup, self._engine.hosts_path)
                self._engine.load()
                self._refresh_list()
                self._set_status(f"Restored from {backup}")
            except OSError as e:
                self._set_status(f"Restore failed: {e}")
        dialog.destroy()

    def _on_close(self, win, event):
        if self._modified:
            dlg = Gtk.MessageDialog(
                parent=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE, text="Save changes before closing?",
            )
            dlg.add_buttons("Discard", Gtk.ResponseType.NO, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.YES)
            resp = dlg.run()
            dlg.destroy()
            if resp == Gtk.ResponseType.YES:
                self._on_save(None)
            elif resp == Gtk.ResponseType.CANCEL:
                return True  # don't close
        return False
