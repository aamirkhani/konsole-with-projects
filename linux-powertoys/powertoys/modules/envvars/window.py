"""Environment Variables GTK3 window - full editor UI."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from typing import Optional
from .engine import EnvVarsEngine, EnvVar, PROFILE_FILES

COL_NAME = 0
COL_VALUE = 1
COL_SOURCE = 2
COL_MODIFIED = 3


class _VarDialog(Gtk.Dialog):
    def __init__(self, parent, var: EnvVar = None):
        title = "Edit Variable" if var else "New Variable"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(500, 260)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_border_width(16)
        self.get_content_area().add(grid)

        grid.attach(Gtk.Label(label="Name:", xalign=1), 0, 0, 1, 1)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_placeholder_text("e.g. MY_VARIABLE")
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Value:", xalign=1), 0, 1, 1, 1)
        self.value_entry = Gtk.Entry()
        self.value_entry.set_hexpand(True)
        grid.attach(self.value_entry, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Save to:", xalign=1), 0, 2, 1, 1)
        self.scope_combo = Gtk.ComboBoxText()
        for s in ["Session only", "User profile (~/.profile)", "System (/etc/environment)"]:
            self.scope_combo.append_text(s)
        self.scope_combo.set_active(0)
        grid.attach(self.scope_combo, 1, 2, 1, 1)

        self._error_lbl = Gtk.Label(xalign=0)
        grid.attach(self._error_lbl, 0, 3, 2, 1)

        # PATH hint
        hint = Gtk.Label(xalign=0)
        hint.set_markup("<small>For PATH-like variables, separate entries with :</small>")
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 0, 4, 2, 1)

        if var:
            self.name_entry.set_text(var.name)
            self.value_entry.set_text(var.value)
            scope_map = {"session": 0, "profile": 1, "system": 2}
            self.scope_combo.set_active(scope_map.get(var.source, 0))
            if var.source != "session":  # Don't edit built-in names
                self.name_entry.set_editable(False)
                self.name_entry.set_sensitive(False)

        self.show_all()

    def get_var(self) -> EnvVar:
        scope_map = {0: "session", 1: "profile", 2: "system"}
        return EnvVar(
            name=self.name_entry.get_text().strip(),
            value=self.value_entry.get_text(),
            source=scope_map.get(self.scope_combo.get_active(), "session"),
        )

    def show_error(self, msg: str):
        self._error_lbl.set_markup(f"<span foreground='red'>{msg}</span>")


class _PathEditor(Gtk.Dialog):
    """Visual editor for PATH-like variables with drag reordering."""

    def __init__(self, parent, path_str: str, var_name: str = "PATH"):
        super().__init__(title=f"Edit {var_name}", transient_for=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(560, 400)

        self._store = Gtk.ListStore(str)
        for entry in path_str.split(":"):
            if entry:
                self._store.append([entry])

        content = self.get_content_area()
        content.set_border_width(8)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{var_name}</b> entries (drag to reorder):")
        content.pack_start(lbl, False, False, 4)

        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_reorderable(True)
        rend = Gtk.CellRendererText()
        rend.set_property("editable", True)
        rend.connect("edited", self._on_edited)
        col = Gtk.TreeViewColumn("Directory", rend, text=0)
        col.set_expand(True)
        self._tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        content.pack_start(scroll, True, True, 0)

        btn_box = Gtk.Box(spacing=4)
        btn_box.set_border_width(4)
        btn_add = Gtk.Button(label="+ Add")
        btn_add.connect("clicked", self._on_add)
        btn_box.pack_start(btn_add, False, False, 0)
        btn_del = Gtk.Button(label="Remove")
        btn_del.connect("clicked", self._on_remove)
        btn_box.pack_start(btn_del, False, False, 0)
        btn_browse = Gtk.Button(label="Browse…")
        btn_browse.connect("clicked", self._on_browse)
        btn_box.pack_start(btn_browse, False, False, 0)
        content.pack_start(btn_box, False, False, 0)

        self.show_all()

    def _on_edited(self, renderer, path, new_text):
        it = self._store.get_iter(path)
        self._store.set_value(it, 0, new_text)

    def _on_add(self, btn):
        self._store.append(["/usr/local/bin"])
        # Select new row
        it = self._store.iter_nth_child(None, len(self._store) - 1)
        if it:
            self._tree.get_selection().select_iter(it)

    def _on_remove(self, btn):
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it:
            self._store.remove(it)

    def _on_browse(self, btn):
        dlg = Gtk.FileChooserDialog(
            title="Select Directory", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            self._store.append([dlg.get_filename()])
        dlg.destroy()

    def get_path_string(self) -> str:
        entries = [self._store.get_value(it, 0) for it in self._iter_store()]
        return ":".join(e for e in entries if e)

    def _iter_store(self):
        it = self._store.get_iter_first()
        while it:
            yield it
            it = self._store.iter_next(it)


class EnvVarsWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Environment Variables")
        self.set_default_size(900, 580)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = EnvVarsEngine()
        self._current_source = "all"
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        hbox = Gtk.Box(spacing=0)
        vbox.pack_start(hbox, True, True, 0)

        hbox.pack_start(self._build_sidebar(), False, False, 0)
        hbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        hbox.pack_start(self._build_main_panel(), True, True, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)
        self.show_all()

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        btn_add = Gtk.Button(label="+ New Variable")
        btn_add.get_style_context().add_class("suggested-action")
        btn_add.connect("clicked", self._on_add)
        bar.pack_start(btn_add, False, False, 0)

        btn_edit = Gtk.Button(label="Edit")
        btn_edit.connect("clicked", lambda *a: self._on_edit())
        bar.pack_start(btn_edit, False, False, 0)

        btn_del = Gtk.Button(label="Delete")
        btn_del.connect("clicked", self._on_delete)
        bar.pack_start(btn_del, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_path = Gtk.Button(label="Edit PATH…")
        btn_path.connect("clicked", self._on_edit_path)
        bar.pack_start(btn_path, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_export = Gtk.Button(label="Export as Script")
        btn_export.connect("clicked", self._on_export)
        bar.pack_start(btn_export, False, False, 0)

        return bar

    def _build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_size_request(160, -1)

        for label, source in [("All", "all"), ("Session", "session"), ("Profile", "profile"), ("System", "system")]:
            btn = Gtk.Button(label=label)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_hexpand(True)
            btn.connect("clicked", self._on_source_changed, source)
            box.pack_start(btn, False, False, 0)

        return box

    def _build_main_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search
        search_box = Gtk.Box(spacing=6)
        search_box.set_border_width(6)
        search_box.pack_start(Gtk.Label(label="Search:"), False, False, 0)
        self._search = Gtk.SearchEntry()
        self._search.set_hexpand(True)
        self._search.connect("search-changed", lambda *a: self._apply_filter())
        search_box.pack_start(self._search, True, True, 0)
        box.pack_start(search_box, False, False, 0)

        # Variable list
        self._store = Gtk.ListStore(str, str, str, bool)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._row_visible)

        self._tree = Gtk.TreeView(model=self._filter)
        self._tree.set_headers_visible(True)
        self._tree.connect("row-activated", lambda t, p, c: self._on_edit())

        for title, col_id, expand, mono in [
            ("Variable", COL_NAME, False, False),
            ("Value", COL_VALUE, True, True),
            ("Source", COL_SOURCE, False, False),
        ]:
            rend = Gtk.CellRendererText()
            if mono:
                rend.set_property("family", "Monospace")
                rend.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, rend, text=col_id)
            col.set_expand(expand)
            col.set_resizable(True)
            col.set_sort_column_id(col_id)
            if not expand:
                col.set_fixed_width(120)
            self._tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        # Value detail
        box.pack_start(Gtk.Separator(), False, False, 0)
        self._detail_buf = Gtk.TextBuffer()
        detail_view = Gtk.TextView(buffer=self._detail_buf)
        detail_view.set_editable(False)
        detail_view.set_size_request(-1, 60)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_min_content_height(60)
        detail_scroll.add(detail_view)
        box.pack_start(detail_scroll, False, False, 0)

        self._tree.get_selection().connect("changed", self._on_selection)

        return box

    def _refresh(self):
        self._store.clear()
        vars_list = self._engine.get_all(self._current_source)
        for v in vars_list:
            self._store.append([v.name, v.value, v.source, v.modified])
        self._set_status(f"{len(vars_list)} variable(s)")

    def _apply_filter(self):
        self._filter.refilter()

    def _row_visible(self, model, it, data):
        q = self._search.get_text().lower() if hasattr(self, "_search") else ""
        if not q:
            return True
        name = model.get_value(it, COL_NAME).lower()
        val = model.get_value(it, COL_VALUE).lower()
        return q in name or q in val

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _get_selected_name(self) -> Optional[str]:
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it is None:
            return None
        child_it = model.convert_iter_to_child_iter(it)
        return self._store.get_value(child_it, COL_NAME)

    def _on_source_changed(self, btn, source: str):
        self._current_source = source
        self._refresh()

    def _on_selection(self, sel):
        model, it = sel.get_selected()
        if it:
            child_it = model.convert_iter_to_child_iter(it)
            val = self._store.get_value(child_it, COL_VALUE)
            self._detail_buf.set_text(val)

    def _on_add(self, btn):
        dlg = _VarDialog(self)
        while True:
            resp = dlg.run()
            if resp != Gtk.ResponseType.OK:
                break
            var = dlg.get_var()
            err = var.validate()
            if err:
                dlg.show_error(err)
                continue
            if var.source == "session":
                self._engine.set_session(var.name, var.value)
            elif var.source == "profile":
                err = self._engine.save_to_profile(var)
            elif var.source == "system":
                err = self._engine.save_to_system(var)
            if err:
                dlg.show_error(err)
                continue
            self._refresh()
            break
        dlg.destroy()

    def _on_edit(self):
        name = self._get_selected_name()
        if not name:
            return
        all_vars = {v.name: v for v in self._engine.get_all()}
        var = all_vars.get(name)
        if not var:
            return
        if var.is_path_var:
            self._on_edit_path(None, var)
            return
        dlg = _VarDialog(self, var)
        while True:
            resp = dlg.run()
            if resp != Gtk.ResponseType.OK:
                break
            new_var = dlg.get_var()
            if var.source == "session":
                self._engine.set_session(new_var.name, new_var.value)
            elif var.source == "profile":
                err = self._engine.save_to_profile(new_var)
                if err:
                    dlg.show_error(err)
                    continue
            self._refresh()
            break
        dlg.destroy()

    def _on_delete(self, btn):
        name = self._get_selected_name()
        if not name:
            return
        dlg = Gtk.MessageDialog(
            parent=self, flags=0, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO, text=f"Delete variable '{name}'?",
        )
        dlg.format_secondary_text("This removes it from the current session only.")
        if dlg.run() == Gtk.ResponseType.YES:
            self._engine.delete_session(name)
            self._refresh()
        dlg.destroy()

    def _on_edit_path(self, btn, var: EnvVar = None):
        if var is None:
            var_name = "PATH"
            path_str = ":".join(self._engine.get_path_entries())
        else:
            var_name = var.name
            path_str = var.value

        dlg = _PathEditor(self, path_str, var_name)
        if dlg.run() == Gtk.ResponseType.OK:
            new_path = dlg.get_path_string()
            self._engine.set_session(var_name, new_path)
            self._refresh()
        dlg.destroy()

    def _on_export(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Export Variables", parent=self, action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("env_export.sh")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            script = self._engine.export_as_shell(self._engine.get_all(self._current_source))
            with open(path, "w") as f:
                f.write(script)
            import os
            os.chmod(path, 0o755)
            self._set_status(f"Exported to {path}")
        dialog.destroy()

