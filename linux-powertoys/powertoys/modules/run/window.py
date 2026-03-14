"""PowerToys Run GTK3 window - spotlight-style quick launcher."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

import threading
from .launcher import RunEngine, RunResult

COL_ICON = 0
COL_TITLE = 1
COL_SUBTITLE = 2
COL_CATEGORY = 3
COL_IDX = 4


class RunWindow(Gtk.Window):
    """Floating search bar that appears on hotkey (Alt+Space by default)."""

    def __init__(self, parent=None):
        super().__init__(title="PowerToys Run")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_default_size(640, 60)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        # Center on screen
        screen = Gdk.Screen.get_default()
        if screen:
            sw = screen.get_width()
            sh = screen.get_height()
            self.move(sw // 2 - 320, sh // 4)

        self._engine = RunEngine()
        self._results: list[RunResult] = []
        self._search_id = 0

        self._build_ui()
        self.connect("key-press-event", self._on_key)

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self._outer)

        # Search bar
        search_box = Gtk.Box(spacing=8)
        search_box.set_border_width(8)
        search_box.get_style_context().add_class("run-searchbar")

        self._search_icon = Gtk.Image.new_from_icon_name("system-search", Gtk.IconSize.LARGE_TOOLBAR)
        search_box.pack_start(self._search_icon, False, False, 0)

        self._entry = Gtk.SearchEntry()
        self._entry.set_placeholder_text("Start typing to search apps, files, or calculate…")
        self._entry.set_hexpand(True)
        self._entry.connect("search-changed", self._on_changed)
        self._entry.connect("activate", self._on_activate)
        search_box.pack_start(self._entry, True, True, 0)

        self._spinner = Gtk.Spinner()
        search_box.pack_start(self._spinner, False, False, 0)

        self._outer.pack_start(search_box, False, False, 0)

        # Results popover-like list
        self._result_revealer = Gtk.Revealer()
        self._result_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)

        result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        result_box.get_style_context().add_class("run-results")

        self._store = Gtk.ListStore(str, str, str, str, int)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(False)
        self._tree.set_activate_on_single_click(False)
        self._tree.connect("row-activated", self._on_row_activated)

        # Icon col
        rend_icon = Gtk.CellRendererPixbuf()
        col_icon = Gtk.TreeViewColumn("", rend_icon)
        col_icon.set_cell_data_func(rend_icon, self._icon_cell_func)
        col_icon.set_fixed_width(42)
        self._tree.append_column(col_icon)

        # Title + subtitle
        rend_text = Gtk.CellRendererText()
        col_text = Gtk.TreeViewColumn("Result", rend_text)
        col_text.set_cell_data_func(rend_text, self._text_cell_func)
        col_text.set_expand(True)
        self._tree.append_column(col_text)

        # Category badge
        rend_cat = Gtk.CellRendererText()
        rend_cat.set_property("xalign", 1.0)
        rend_cat.set_property("foreground", "gray")
        rend_cat.set_property("scale", 0.85)
        col_cat = Gtk.TreeViewColumn("", rend_cat, text=COL_CATEGORY)
        col_cat.set_fixed_width(100)
        self._tree.append_column(col_cat)

        result_box.pack_start(self._tree, True, True, 0)
        self._result_revealer.add(result_box)
        self._outer.pack_start(self._result_revealer, False, False, 0)

        self._apply_css()
        self.show_all()
        self._result_revealer.set_reveal_child(False)
        self._spinner.set_no_show_all(True)
        self.grab_focus()
        self._entry.grab_focus()

    def _apply_css(self):
        css = b"""
        window { border-radius: 12px; border: 1px solid #ccc; }
        .run-searchbar { background: #1e1e1e; border-radius: 12px 12px 0 0; }
        entry { background: transparent; color: white; border: none; box-shadow: none; font-size: 18px; }
        entry:focus { border: none; box-shadow: none; }
        treeview { background: #252526; color: #d4d4d4; font-size: 14px; }
        treeview:selected { background: #094771; color: white; }
        """
        prov = Gtk.CssProvider()
        prov.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _icon_cell_func(self, col, renderer, model, it, data):
        icon_name = model.get_value(it, COL_ICON)
        try:
            theme = Gtk.IconTheme.get_default()
            if theme.has_icon(icon_name):
                pixbuf = theme.load_icon(icon_name, 32, 0)
                renderer.set_property("pixbuf", pixbuf)
                return
        except Exception:
            pass
        renderer.set_property("icon-name", "application-x-executable")

    def _text_cell_func(self, col, renderer, model, it, data):
        title = model.get_value(it, COL_TITLE)
        subtitle = model.get_value(it, COL_SUBTITLE)
        markup = f"<b>{GLib.markup_escape_text(title)}</b>"
        if subtitle:
            markup += f"\n<small>{GLib.markup_escape_text(subtitle[:80])}</small>"
        renderer.set_property("markup", markup)

    # ── Search logic ───────────────────────────────────────────────────────

    def _on_changed(self, entry):
        self._search_id += 1
        sid = self._search_id
        query = entry.get_text()
        if not query.strip():
            self._store.clear()
            self._result_revealer.set_reveal_child(False)
            return
        self._spinner.show()
        self._spinner.start()

        def run():
            results = self._engine.search(query)
            GLib.idle_add(lambda: self._populate_results(results, sid))

        threading.Thread(target=run, daemon=True).start()

    def _populate_results(self, results: list, sid: int):
        if sid != self._search_id:
            return
        self._spinner.stop()
        self._spinner.hide()
        self._results = results
        self._store.clear()
        for i, r in enumerate(results):
            self._store.append([r.icon, r.title, r.subtitle, r.category, i])
        has = len(results) > 0
        self._result_revealer.set_reveal_child(has)
        if has:
            # Resize window to fit up to 6 results
            h = min(len(results), 6) * 58 + 60
            self.resize(640, h)
            self._tree.get_selection().select_path(Gtk.TreePath.new_first())

    def _on_activate(self, entry):
        """Run top result on Enter."""
        sel = self._tree.get_selection()
        model, it = sel.get_selected()
        if it is None and self._store.get_iter_first():
            it = self._store.get_iter_first()
        if it:
            idx = self._store.get_value(it, COL_IDX)
            self._run(idx)

    def _on_row_activated(self, tree, path, col):
        it = self._store.get_iter(path)
        idx = self._store.get_value(it, COL_IDX)
        self._run(idx)

    def _run(self, idx: int):
        if 0 <= idx < len(self._results):
            try:
                self._results[idx].execute()
            except Exception as e:
                print(f"Run error: {e}")
        self._entry.set_text("")
        self._result_revealer.set_reveal_child(False)
        self.hide()

    def _on_key(self, widget, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_Escape:
            self._entry.set_text("")
            self.hide()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            self._tree.grab_focus()
            return False
        return False
