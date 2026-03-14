"""ClipboardHistory GTK3 window - full clipboard manager UI."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from .history import ClipboardEngine, ClipboardEntry

COL_PINNED = 0
COL_PREVIEW = 1
COL_TIMESTAMP = 2
COL_SIZE = 3
COL_IDX = 4


class ClipboardWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Clipboard History")
        self.set_default_size(620, 500)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = ClipboardEngine()
        self._engine.on_change(self._on_new_entry)
        self._engine.start_monitoring()

        self._build_ui()
        self._refresh_list()
        self.connect("destroy", lambda w: self._engine.stop_monitoring())

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Search
        search_box = Gtk.Box(spacing=6)
        search_box.set_border_width(6)
        search_box.pack_start(Gtk.Label(label="Search:"), False, False, 0)
        self._search = Gtk.SearchEntry()
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search)
        search_box.pack_start(self._search, True, True, 0)
        vbox.pack_start(search_box, False, False, 0)

        # List
        self._store = Gtk.ListStore(bool, str, str, str, int)
        self._filter_model = self._store.filter_new()
        self._filter_model.set_visible_func(self._row_visible)

        self._tree = Gtk.TreeView(model=self._filter_model)
        self._tree.set_headers_visible(True)

        # Pin toggle
        rend_pin = Gtk.CellRendererToggle()
        rend_pin.connect("toggled", self._on_pin_toggled)
        col_pin = Gtk.TreeViewColumn("📌", rend_pin, active=COL_PINNED)
        col_pin.set_fixed_width(40)
        self._tree.append_column(col_pin)

        # Preview
        rend_prev = Gtk.CellRendererText()
        rend_prev.set_property("ellipsize", Pango.EllipsizeMode.END)
        rend_prev.set_property("family", "Monospace")
        col_prev = Gtk.TreeViewColumn("Content", rend_prev, text=COL_PREVIEW)
        col_prev.set_expand(True)
        col_prev.set_resizable(True)
        self._tree.append_column(col_prev)

        # Timestamp
        rend_ts = Gtk.CellRendererText()
        col_ts = Gtk.TreeViewColumn("Time", rend_ts, text=COL_TIMESTAMP)
        col_ts.set_fixed_width(90)
        self._tree.append_column(col_ts)

        # Size
        rend_size = Gtk.CellRendererText()
        col_size = Gtk.TreeViewColumn("Size", rend_size, text=COL_SIZE)
        col_size.set_fixed_width(80)
        self._tree.append_column(col_size)

        self._tree.connect("row-activated", self._on_row_activated)
        self._tree.get_selection().connect("changed", self._on_selection_changed)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        vbox.pack_start(scroll, True, True, 0)

        # Detail panel
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        detail_box.set_size_request(-1, 120)

        detail_header = Gtk.Box(spacing=6)
        detail_header.set_border_width(4)
        self._detail_lbl = Gtk.Label(label="Select an entry to preview", xalign=0)
        detail_header.pack_start(self._detail_lbl, True, True, 0)
        btn_copy = Gtk.Button(label="Copy to Clipboard")
        btn_copy.get_style_context().add_class("suggested-action")
        btn_copy.connect("clicked", self._on_copy_selected)
        detail_header.pack_start(btn_copy, False, False, 0)
        detail_box.pack_start(detail_header, False, False, 0)

        self._detail_buf = Gtk.TextBuffer()
        detail_view = Gtk.TextView(buffer=self._detail_buf)
        detail_view.set_editable(False)
        detail_view.set_wrap_mode(Gtk.WrapMode.WORD)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_min_content_height(80)
        detail_scroll.add(detail_view)
        detail_box.pack_start(detail_scroll, True, True, 0)
        vbox.pack_start(detail_box, False, False, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        btn_clear = Gtk.Button(label="Clear History")
        btn_clear.connect("clicked", self._on_clear)
        bar.pack_start(btn_clear, False, False, 0)

        btn_delete = Gtk.Button(label="Delete Selected")
        btn_delete.connect("clicked", self._on_delete)
        bar.pack_start(btn_delete, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self._monitor_lbl = Gtk.Label()
        bar.pack_end(self._monitor_lbl, False, False, 4)
        self._update_monitor_label()

        btn_toggle_mon = Gtk.Button(label="Pause/Resume")
        btn_toggle_mon.connect("clicked", self._on_toggle_monitor)
        bar.pack_end(btn_toggle_mon, False, False, 0)

        return bar

    def _refresh_list(self):
        self._store.clear()
        for i, entry in enumerate(self._engine.history):
            self._store.append([
                entry.pinned,
                entry.preview,
                entry.timestamp_str,
                entry.size_str,
                i,
            ])
        n = len(self._engine.history)
        self._set_status(f"{n} item(s) in history")

    def _row_visible(self, model, it, data):
        q = self._search.get_text().lower() if hasattr(self, "_search") else ""
        if not q:
            return True
        preview = model.get_value(it, COL_PREVIEW).lower()
        return q in preview

    def _get_selected_entry(self) -> tuple:
        """Returns (entry, store_iter) or (None, None)."""
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it is None:
            return None, None
        child_it = model.convert_iter_to_child_iter(it)
        idx = self._store.get_value(child_it, COL_IDX)
        if 0 <= idx < len(self._engine.history):
            return self._engine.history[idx], child_it
        return None, None

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _update_monitor_label(self):
        if self._engine._running:
            self._monitor_lbl.set_markup("<span foreground='green'>● Monitoring</span>")
        else:
            self._monitor_lbl.set_markup("<span foreground='gray'>● Paused</span>")

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_new_entry(self, entry: ClipboardEntry):
        """Called when clipboard changes (from monitoring thread)."""
        GLib.idle_add(self._refresh_list)

    def _on_search(self, entry):
        self._filter_model.refilter()

    def _on_selection_changed(self, selection):
        entry, _ = self._get_selected_entry()
        if entry:
            self._detail_buf.set_text(entry.content[:5000])
            self._detail_lbl.set_text(f"{entry.timestamp_str}  •  {entry.size_str}")

    def _on_row_activated(self, tree, path, col):
        """Double-click: copy to clipboard."""
        self._on_copy_selected(None)

    def _on_copy_selected(self, btn):
        entry, _ = self._get_selected_entry()
        if entry:
            self._engine.set_clipboard(entry.content)
            self._set_status("Copied to clipboard")

    def _on_pin_toggled(self, renderer, path):
        it = self._filter_model.get_iter(path)
        child_it = self._filter_model.convert_iter_to_child_iter(it)
        idx = self._store.get_value(child_it, COL_IDX)
        if 0 <= idx < len(self._engine.history):
            entry = self._engine.history[idx]
            self._engine.pin_entry(entry, not entry.pinned)
            self._store.set_value(child_it, COL_PINNED, entry.pinned)

    def _on_delete(self, btn):
        entry, _ = self._get_selected_entry()
        if entry:
            self._engine.delete_entry(entry)
            self._refresh_list()

    def _on_clear(self, btn):
        dlg = Gtk.MessageDialog(
            parent=self, flags=0, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Clear clipboard history?",
        )
        dlg.format_secondary_text("Pinned items will be kept.")
        if dlg.run() == Gtk.ResponseType.YES:
            self._engine.clear_history(keep_pinned=True)
            self._refresh_list()
        dlg.destroy()

    def _on_toggle_monitor(self, btn):
        if self._engine._running:
            self._engine.stop_monitoring()
        else:
            self._engine.start_monitoring()
        self._update_monitor_label()
