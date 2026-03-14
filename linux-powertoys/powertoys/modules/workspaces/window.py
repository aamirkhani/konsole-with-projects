"""Workspaces GTK3 window - save and restore window layouts."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .engine import WorkspacesEngine, Workspace

COL_NAME = 0
COL_DESC = 1
COL_WIN_COUNT = 2


class _CaptureDialog(Gtk.Dialog):
    def __init__(self, parent, existing_names):
        super().__init__(title="Save Workspace", parent=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Save", Gtk.ResponseType.OK
        )
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="Name:", xalign=0), 0, 0, 1, 1)
        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("e.g. Development, Design, Gaming")
        grid.attach(self._name_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Description:", xalign=0), 0, 1, 1, 1)
        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("Optional description")
        grid.attach(self._desc_entry, 1, 1, 1, 1)

        if existing_names:
            warn = Gtk.Label(xalign=0)
            warn.set_markup(
                "<small><i>Existing names: " + ", ".join(existing_names) + "</i></small>"
            )
            grid.attach(warn, 0, 2, 2, 1)

        self.get_content_area().add(grid)
        self.show_all()

    @property
    def workspace_name(self) -> str:
        return self._name_entry.get_text().strip()

    @property
    def workspace_description(self) -> str:
        return self._desc_entry.get_text().strip()


class _WindowListDialog(Gtk.Dialog):
    """Show the windows saved in a workspace."""

    def __init__(self, parent, workspace: Workspace):
        super().__init__(title=f"Windows in '{workspace.name}'", parent=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(600, 350)

        store = Gtk.ListStore(str, str, int, int, int, int)
        for w in workspace.windows:
            store.append([w.title, w.process_name, w.x, w.y, w.width, w.height])

        tree = Gtk.TreeView(model=store)
        for col_idx, (title, expand) in enumerate([
            ("Title", True), ("Process", False),
            ("X", False), ("Y", False), ("Width", False), ("Height", False)
        ]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=col_idx)
            col.set_expand(expand)
            if not expand:
                col.set_min_width(70)
            tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.add(tree)
        scroll.set_size_request(-1, 280)

        self.get_content_area().add(scroll)
        self.show_all()


class WorkspacesWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Workspaces")
        self.set_default_size(700, 500)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = WorkspacesEngine()
        self._build_ui()
        self._populate()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Toolbar
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(8)

        btn_capture = Gtk.Button(label="Save Current Layout…")
        btn_capture.get_style_context().add_class("suggested-action")
        btn_capture.connect("clicked", self._on_capture)
        bar.pack_start(btn_capture, False, False, 0)

        btn_restore = Gtk.Button(label="Restore Selected")
        btn_restore.connect("clicked", self._on_restore)
        bar.pack_start(btn_restore, False, False, 0)

        btn_view = Gtk.Button(label="View Windows")
        btn_view.connect("clicked", self._on_view_windows)
        bar.pack_start(btn_view, False, False, 0)

        btn_delete = Gtk.Button(label="Delete")
        btn_delete.connect("clicked", self._on_delete)
        bar.pack_start(btn_delete, False, False, 0)

        btn_refresh = Gtk.Button(label="Refresh")
        btn_refresh.connect("clicked", lambda *a: self._populate())
        bar.pack_end(btn_refresh, False, False, 0)

        vbox.pack_start(bar, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Split: workspace list | current windows
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_border_width(4)

        # Saved workspaces list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left_lbl = Gtk.Label(xalign=0)
        left_lbl.set_markup("<b>Saved Workspaces</b>")
        left_lbl.set_border_width(4)
        left_box.pack_start(left_lbl, False, False, 0)

        self._ws_store = Gtk.ListStore(str, str, int)
        self._ws_tree = Gtk.TreeView(model=self._ws_store)
        self._ws_tree.set_headers_visible(True)

        for col_idx, (title, expand) in enumerate([
            ("Name", True), ("Description", True), ("Windows", False)
        ]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=col_idx)
            col.set_expand(expand)
            if not expand:
                col.set_min_width(70)
            self._ws_tree.append_column(col)

        self._ws_tree.get_selection().connect("changed", self._on_selection_changed)
        self._ws_tree.connect("row-activated", self._on_row_activated)

        scroll_left = Gtk.ScrolledWindow()
        scroll_left.add(self._ws_tree)
        left_box.pack_start(scroll_left, True, True, 0)
        paned.pack1(left_box, True, False)

        # Current windows preview
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_lbl = Gtk.Label(xalign=0)
        right_lbl.set_markup("<b>Current Open Windows</b>")
        right_lbl.set_border_width(4)
        right_box.pack_start(right_lbl, False, False, 0)

        self._cur_store = Gtk.ListStore(str, str, int, int)
        self._cur_tree = Gtk.TreeView(model=self._cur_store)
        for col_idx, (title, expand) in enumerate([
            ("Title", True), ("Process", False), ("Width", False), ("Height", False)
        ]):
            rend = Gtk.CellRendererText()
            rend.set_property("ellipsize", 3)
            col = Gtk.TreeViewColumn(title, rend, text=col_idx)
            col.set_expand(expand)
            self._cur_tree.append_column(col)

        scroll_right = Gtk.ScrolledWindow()
        scroll_right.add(self._cur_tree)
        right_box.pack_start(scroll_right, True, True, 0)

        btn_refresh_cur = Gtk.Button(label="Refresh Current Windows")
        btn_refresh_cur.connect("clicked", self._on_refresh_current)
        right_box.pack_start(btn_refresh_cur, False, False, 0)

        paned.pack2(right_box, True, False)
        paned.set_position(300)

        vbox.pack_start(paned, True, True, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()
        self._on_refresh_current(None)

    def _populate(self):
        self._ws_store.clear()
        for ws in self._engine.workspaces:
            self._ws_store.append([ws.name, ws.description, len(ws.windows)])
        self._set_status(f"{len(self._engine.workspaces)} saved workspace(s)")

    def _on_refresh_current(self, btn):
        self._cur_store.clear()
        windows = self._engine.get_current_windows()
        for w in windows:
            self._cur_store.append([w.title, w.process_name, w.width, w.height])

    def _on_selection_changed(self, selection):
        model, it = selection.get_selected()
        has_sel = it is not None
        # Could update a detail panel here

    def _on_row_activated(self, tree, path, col):
        self._on_restore(None)

    def _get_selected_workspace(self):
        model, it = self._ws_tree.get_selection().get_selected()
        if it is None:
            return None
        name = model[it][COL_NAME]
        for ws in self._engine.workspaces:
            if ws.name == name:
                return ws
        return None

    def _on_capture(self, btn):
        existing = [ws.name for ws in self._engine.workspaces]
        dialog = _CaptureDialog(self, existing)
        if dialog.run() == Gtk.ResponseType.OK:
            name = dialog.workspace_name
            desc = dialog.workspace_description
            if name:
                ws = self._engine.capture(name, desc)
                self._populate()
                self._set_status(
                    f"Saved workspace '{name}' with {len(ws.windows)} window(s)"
                )
            else:
                self._set_status("Name cannot be empty")
        dialog.destroy()

    def _on_restore(self, btn):
        ws = self._get_selected_workspace()
        if ws is None:
            self._set_status("Select a workspace to restore")
            return
        ok, fail = self._engine.restore(ws)
        self._set_status(
            f"Restored '{ws.name}': {ok} window(s) moved, {fail} not found"
        )

    def _on_view_windows(self, btn):
        ws = self._get_selected_workspace()
        if ws is None:
            return
        dialog = _WindowListDialog(self, ws)
        dialog.run()
        dialog.destroy()

    def _on_delete(self, btn):
        ws = self._get_selected_workspace()
        if ws is None:
            return
        confirm = Gtk.MessageDialog(
            parent=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete workspace '{ws.name}'?"
        )
        if confirm.run() == Gtk.ResponseType.YES:
            self._engine.delete(ws.name)
            self._populate()
        confirm.destroy()

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)
