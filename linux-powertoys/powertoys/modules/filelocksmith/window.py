"""FileLocksmith GTK3 window - full UI for file handle inspection."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import threading
from pathlib import Path

from .engine import FileLocksmithEngine, FileHandle

COL_PID = 0
COL_NAME = 1
COL_USER = 2
COL_FILE = 3
COL_TYPE = 4
COL_ACCESS = 5


class FileLocksmithWindow(Gtk.Window):
    def __init__(self, path: str = None, parent=None):
        super().__init__(title="File Locksmith")
        self.set_default_size(900, 550)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = FileLocksmithEngine()
        self._handles = []
        self._searching = False

        self._build_ui()

        if path:
            self._path_entry.set_text(path)
            self._search()

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Search bar
        search_bar = Gtk.Box(spacing=6)
        search_bar.set_border_width(8)

        lbl = Gtk.Label(label="File or Directory:")
        search_bar.pack_start(lbl, False, False, 0)

        self._path_entry = Gtk.Entry()
        self._path_entry.set_placeholder_text("Enter file or directory path…")
        self._path_entry.set_hexpand(True)
        self._path_entry.connect("activate", lambda *a: self._search())
        search_bar.pack_start(self._path_entry, True, True, 0)

        btn_browse = Gtk.Button(label="Browse…")
        btn_browse.connect("clicked", self._on_browse)
        search_bar.pack_start(btn_browse, False, False, 0)

        self._btn_search = Gtk.Button(label="Find Handles")
        self._btn_search.get_style_context().add_class("suggested-action")
        self._btn_search.connect("clicked", lambda *a: self._search())
        search_bar.pack_start(self._btn_search, False, False, 0)

        vbox.pack_start(search_bar, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Info bar for results summary
        self._info_bar = Gtk.InfoBar()
        self._info_bar.set_message_type(Gtk.MessageType.INFO)
        self._info_label = Gtk.Label(label="Enter a path and click Find Handles")
        self._info_bar.get_content_area().add(self._info_label)
        self._info_bar.set_no_show_all(False)
        vbox.pack_start(self._info_bar, False, False, 0)

        # Process list
        vbox.pack_start(self._build_list(), True, True, 0)

        # Action bar
        vbox.pack_start(self._build_action_bar(), False, False, 0)

        # Spinner overlay
        self._spinner = Gtk.Spinner()
        self._spinner.set_no_show_all(True)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

    def _build_list(self):
        self._store = Gtk.ListStore(int, str, str, str, str, str)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._row_visible)
        self._sort = Gtk.TreeModelSort(model=self._filter)

        self._tree = Gtk.TreeView(model=self._sort)
        self._tree.set_headers_clickable(True)

        columns = [
            ("PID", COL_PID, 70, int),
            ("Process", COL_NAME, 150, str),
            ("User", COL_USER, 100, str),
            ("File / Path", COL_FILE, 300, str),
            ("Type", COL_TYPE, 70, str),
            ("Access", COL_ACCESS, 90, str),
        ]
        for title, col_id, width, _ in columns:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            col.set_sort_column_id(col_id)
            if col_id == COL_FILE:
                col.set_expand(True)
                renderer.set_property("ellipsize", 3)  # MIDDLE
            self._tree.append_column(col)

        self._tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        return scroll

    def _build_action_bar(self):
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(6)

        # Filter box
        bar.pack_start(Gtk.Label(label="Filter:"), False, False, 0)
        self._filter_entry = Gtk.SearchEntry()
        self._filter_entry.set_placeholder_text("Filter by process, user or path…")
        self._filter_entry.connect("search-changed", lambda *a: self._filter.refilter())
        bar.pack_start(self._filter_entry, True, True, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self._btn_term = Gtk.Button(label="Terminate Process")
        self._btn_term.connect("clicked", self._on_terminate)
        bar.pack_start(self._btn_term, False, False, 0)

        self._btn_kill = Gtk.Button(label="Force Kill")
        self._btn_kill.get_style_context().add_class("destructive-action")
        self._btn_kill.connect("clicked", self._on_force_kill)
        bar.pack_start(self._btn_kill, False, False, 0)

        self._btn_copy = Gtk.Button(label="Copy PID(s)")
        self._btn_copy.connect("clicked", self._on_copy_pids)
        bar.pack_start(self._btn_copy, False, False, 0)

        return bar

    # ── Logic ──────────────────────────────────────────────────────────────

    def _row_visible(self, model, it, data):
        query = self._filter_entry.get_text().lower() if hasattr(self, "_filter_entry") else ""
        if not query:
            return True
        for col in (COL_NAME, COL_USER, COL_FILE):
            val = model.get_value(it, col) or ""
            if query in val.lower():
                return True
        pid = str(model.get_value(it, COL_PID))
        return query in pid

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _search(self):
        path = self._path_entry.get_text().strip()
        if not path or self._searching:
            return

        self._searching = True
        self._btn_search.set_sensitive(False)
        self._store.clear()
        self._set_status("Searching…")
        self._info_label.set_text("Searching for open handles…")

        def run():
            handles = self._engine.find(path)
            GLib.idle_add(self._on_results, handles)

        threading.Thread(target=run, daemon=True).start()

    def _on_results(self, handles):
        self._handles = handles
        self._store.clear()
        for h in handles:
            self._store.append([
                h.pid, h.process_name, h.user, h.file_path, h.fd_type, h.display_access,
            ])
        count = len(handles)
        pids = len(set(h.pid for h in handles))
        msg = f"{count} handle(s) from {pids} process(es)"
        self._info_label.set_text(msg)
        self._set_status(f"Found {count} open handle(s)")
        self._searching = False
        self._btn_search.set_sensitive(True)

    def _get_selected_pids(self) -> list:
        sel = self._tree.get_selection()
        model, paths = sel.get_selected_rows()
        pids = []
        for path in paths:
            it = model.get_iter(path)
            # Resolve through sort → filter → store
            child_it = model.convert_iter_to_child_iter(it)
            filter_it = self._sort.get_model().convert_iter_to_child_iter(child_it)
            pid = self._store.get_value(filter_it, COL_PID)
            if pid not in pids:
                pids.append(pid)
        return pids

    def _confirm_kill(self, pids: list, force: bool) -> bool:
        action = "force kill" if force else "terminate"
        msg = Gtk.MessageDialog(
            parent=self, flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Are you sure you want to {action} PID(s): {', '.join(str(p) for p in pids)}?",
        )
        resp = msg.run()
        msg.destroy()
        return resp == Gtk.ResponseType.YES

    def _on_terminate(self, btn):
        pids = self._get_selected_pids()
        if not pids or not self._confirm_kill(pids, False):
            return
        for pid in pids:
            self._engine.kill_process(pid, force=False)
        self._search()

    def _on_force_kill(self, btn):
        pids = self._get_selected_pids()
        if not pids or not self._confirm_kill(pids, True):
            return
        for pid in pids:
            self._engine.kill_process(pid, force=True)
        self._search()

    def _on_copy_pids(self, btn):
        pids = self._get_selected_pids()
        if pids:
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clip.set_text(", ".join(str(p) for p in pids), -1)

    def _on_browse(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Select File or Folder", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self._path_entry.set_text(dialog.get_filename())
        dialog.destroy()
