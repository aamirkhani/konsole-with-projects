"""ShortcutGuide GTK3 window - keyboard shortcut reference."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .engine import ShortcutGuideEngine, ShortcutEntry, get_categories, get_contexts

COL_KEYS = 0
COL_DESC = 1
COL_CONTEXT = 2
COL_CATEGORY = 3


class _AddShortcutDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Add Custom Shortcut", parent=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="Keys:", xalign=0), 0, 0, 1, 1)
        self._keys_entry = Gtk.Entry()
        self._keys_entry.set_placeholder_text("e.g. Ctrl+Shift+P")
        grid.attach(self._keys_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Description:", xalign=0), 0, 1, 1, 1)
        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("What does this shortcut do?")
        grid.attach(self._desc_entry, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Category:", xalign=0), 0, 2, 1, 1)
        self._cat_entry = Gtk.Entry()
        self._cat_entry.set_text("Custom")
        grid.attach(self._cat_entry, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Context:", xalign=0), 0, 3, 1, 1)
        self._ctx_entry = Gtk.Entry()
        self._ctx_entry.set_text("Global")
        grid.attach(self._ctx_entry, 1, 3, 1, 1)

        self.get_content_area().add(grid)
        self.show_all()

    def get_entry(self) -> ShortcutEntry:
        return ShortcutEntry(
            keys=self._keys_entry.get_text().strip(),
            description=self._desc_entry.get_text().strip(),
            category=self._cat_entry.get_text().strip() or "Custom",
            context=self._ctx_entry.get_text().strip() or "Global",
        )


class ShortcutGuideWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Shortcut Guide")
        self.set_default_size(860, 600)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = ShortcutGuideEngine()
        self._build_ui()
        self._populate()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Toolbar
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(8)

        # Search
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search shortcuts…")
        search.set_size_request(260, -1)
        search.connect("search-changed", self._on_search)
        bar.pack_start(search, False, False, 0)

        # Category filter
        bar.pack_start(Gtk.Label(label="Category:"), False, False, 0)
        self._cat_combo = Gtk.ComboBoxText()
        for cat in get_categories():
            self._cat_combo.append_text(cat)
        self._cat_combo.set_active(0)
        self._cat_combo.connect("changed", self._on_filter_changed)
        bar.pack_start(self._cat_combo, False, False, 0)

        # Context filter
        bar.pack_start(Gtk.Label(label="Context:"), False, False, 0)
        self._ctx_combo = Gtk.ComboBoxText()
        for ctx in get_contexts():
            self._ctx_combo.append_text(ctx)
        self._ctx_combo.set_active(0)
        self._ctx_combo.connect("changed", self._on_filter_changed)
        bar.pack_start(self._ctx_combo, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_add = Gtk.Button(label="Add Custom")
        btn_add.connect("clicked", self._on_add)
        bar.pack_start(btn_add, False, False, 0)

        btn_remove = Gtk.Button(label="Remove Selected")
        btn_remove.connect("clicked", self._on_remove)
        bar.pack_start(btn_remove, False, False, 0)

        vbox.pack_start(bar, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # TreeView
        self._store = Gtk.ListStore(str, str, str, str)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._visible_func)

        self._tree = Gtk.TreeView(model=self._filter)
        self._tree.set_headers_visible(True)
        self._tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        # Keys column with styled rendering
        rend_keys = Gtk.CellRendererText()
        rend_keys.set_property("font", "Monospace Bold 10")
        col_keys = Gtk.TreeViewColumn("Shortcut", rend_keys, text=COL_KEYS)
        col_keys.set_min_width(180)
        col_keys.set_sort_column_id(COL_KEYS)
        self._tree.append_column(col_keys)

        rend_desc = Gtk.CellRendererText()
        rend_desc.set_property("ellipsize", 3)
        col_desc = Gtk.TreeViewColumn("Description", rend_desc, text=COL_DESC)
        col_desc.set_expand(True)
        col_desc.set_sort_column_id(COL_DESC)
        self._tree.append_column(col_desc)

        rend_cat = Gtk.CellRendererText()
        col_cat = Gtk.TreeViewColumn("Category", rend_cat, text=COL_CATEGORY)
        col_cat.set_min_width(110)
        col_cat.set_sort_column_id(COL_CATEGORY)
        self._tree.append_column(col_cat)

        rend_ctx = Gtk.CellRendererText()
        col_ctx = Gtk.TreeViewColumn("Context", rend_ctx, text=COL_CONTEXT)
        col_ctx.set_min_width(120)
        col_ctx.set_sort_column_id(COL_CONTEXT)
        self._tree.append_column(col_ctx)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        vbox.pack_start(scroll, True, True, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self._search_query = ""
        self.show_all()

    def _populate(self, shortcuts=None):
        self._store.clear()
        items = shortcuts if shortcuts is not None else self._engine.all_shortcuts
        for s in items:
            self._store.append([s.keys, s.description, s.context, s.category])
        self._update_status(len(items))

    def _update_status(self, count: int):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, f"{count} shortcuts")

    def _on_search(self, entry):
        self._search_query = entry.get_text().strip()
        self._apply_filters()

    def _on_filter_changed(self, combo):
        self._apply_filters()

    def _apply_filters(self):
        cat = self._cat_combo.get_active_text() or "All"
        ctx = self._ctx_combo.get_active_text() or "All"
        q = self._search_query.lower()

        items = self._engine.filter(cat, ctx)
        if q:
            items = [s for s in items if q in s.keys.lower() or q in s.description.lower()]
        self._populate(items)

    def _visible_func(self, model, it, data):
        return True  # filtering done by _apply_filters

    def _on_add(self, btn):
        dialog = _AddShortcutDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            entry = dialog.get_entry()
            if entry.keys and entry.description:
                self._engine.add_custom(entry)
                self._apply_filters()
        dialog.destroy()

    def _on_remove(self, btn):
        model, it = self._tree.get_selection().get_selected()
        if it is None:
            return
        keys = model[it][COL_KEYS]
        desc = model[it][COL_DESC]
        # Only allow removing custom entries
        for i, entry in enumerate(self._engine._custom):
            if entry.keys == keys and entry.description == desc:
                self._engine.remove_custom(i)
                self._apply_filters()
                break
