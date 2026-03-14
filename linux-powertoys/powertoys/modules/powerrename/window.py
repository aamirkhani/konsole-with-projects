"""PowerRename GTK3 window - full UI for batch file renaming."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

import os
import threading
from pathlib import Path
from typing import List

from .engine import PowerRenameEngine, RenameResult, CASE_TRANSFORMS


COL_ORIGINAL = 0
COL_NEW_NAME = 1
COL_STATUS = 2
COL_CHANGED = 3  # bool for row color
COL_ERROR = 4


class PowerRenameWindow(Gtk.Window):
    def __init__(self, paths: List[str] = None, parent=None):
        super().__init__(title="PowerRename")
        self.set_default_size(900, 600)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._paths: List[Path] = [Path(p) for p in (paths or [])]
        self._engine = PowerRenameEngine()
        self._preview_thread = None
        self._preview_id = 0

        self._build_ui()
        self._update_preview()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Toolbar
        toolbar = self._make_toolbar()
        vbox.pack_start(toolbar, False, False, 0)

        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Paned: left = controls, right = file list
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(320)
        vbox.pack_start(paned, True, True, 0)

        paned.add1(self._make_controls_panel())
        paned.add2(self._make_file_list())

        # Status bar
        self._status_bar = Gtk.Statusbar()
        vbox.pack_start(self._status_bar, False, False, 0)

        self.show_all()

    def _make_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_border_width(6)

        btn_open = Gtk.Button(label="Add Files")
        btn_open.connect("clicked", self._on_add_files)
        bar.pack_start(btn_open, False, False, 0)

        btn_dir = Gtk.Button(label="Add Folder")
        btn_dir.connect("clicked", self._on_add_folder)
        bar.pack_start(btn_dir, False, False, 0)

        btn_clear = Gtk.Button(label="Clear List")
        btn_clear.connect("clicked", self._on_clear_list)
        bar.pack_start(btn_clear, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self._btn_rename = Gtk.Button(label="Rename All")
        self._btn_rename.get_style_context().add_class("suggested-action")
        self._btn_rename.connect("clicked", self._on_rename)
        bar.pack_start(self._btn_rename, False, False, 0)

        return bar

    def _make_controls_panel(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_border_width(0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        grid.set_border_width(12)
        scroll.add(grid)

        row = 0

        # ── Search & Replace ─────────────────────────────────────────────
        grid.attach(self._section_label("Search & Replace"), 0, row, 2, 1); row += 1

        grid.attach(Gtk.Label(label="Search:", xalign=0), 0, row, 1, 1)
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Text to find…")
        self._search_entry.connect("search-changed", lambda *a: self._schedule_preview())
        grid.attach(self._search_entry, 1, row, 1, 1); row += 1

        grid.attach(Gtk.Label(label="Replace:", xalign=0), 0, row, 1, 1)
        self._replace_entry = Gtk.Entry()
        self._replace_entry.set_placeholder_text("Replacement text…")
        self._replace_entry.connect("changed", lambda *a: self._schedule_preview())
        grid.attach(self._replace_entry, 1, row, 1, 1); row += 1

        # ── Options ──────────────────────────────────────────────────────
        grid.attach(self._section_label("Options"), 0, row, 2, 1); row += 1

        self._regex_check = Gtk.CheckButton(label="Use regular expressions")
        self._regex_check.connect("toggled", lambda *a: self._schedule_preview())
        grid.attach(self._regex_check, 0, row, 2, 1); row += 1

        self._case_check = Gtk.CheckButton(label="Case sensitive")
        self._case_check.connect("toggled", lambda *a: self._schedule_preview())
        grid.attach(self._case_check, 0, row, 2, 1); row += 1

        self._ext_check = Gtk.CheckButton(label="Apply to file extension")
        self._ext_check.connect("toggled", lambda *a: self._schedule_preview())
        grid.attach(self._ext_check, 0, row, 2, 1); row += 1

        self._recursive_check = Gtk.CheckButton(label="Include subdirectories")
        self._recursive_check.connect("toggled", lambda *a: self._schedule_preview())
        grid.attach(self._recursive_check, 0, row, 2, 1); row += 1

        # ── Case Transform ───────────────────────────────────────────────
        grid.attach(self._section_label("Case Transform"), 0, row, 2, 1); row += 1

        grid.attach(Gtk.Label(label="Transform:", xalign=0), 0, row, 1, 1)
        self._case_combo = Gtk.ComboBoxText()
        for name in CASE_TRANSFORMS:
            self._case_combo.append_text(name)
        self._case_combo.set_active(0)
        self._case_combo.connect("changed", lambda *a: self._schedule_preview())
        grid.attach(self._case_combo, 1, row, 1, 1); row += 1

        # ── Enumeration ──────────────────────────────────────────────────
        grid.attach(self._section_label("Enumeration"), 0, row, 2, 1); row += 1

        self._enum_check = Gtk.CheckButton(label="Append sequential numbers")
        self._enum_check.connect("toggled", self._on_enum_toggle)
        grid.attach(self._enum_check, 0, row, 2, 1); row += 1

        self._enum_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._enum_frame.set_sensitive(False)
        grid.attach(self._enum_frame, 0, row, 2, 1); row += 1

        enum_grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        self._enum_frame.pack_start(enum_grid, False, False, 0)

        enum_grid.attach(Gtk.Label(label="Start:", xalign=0), 0, 0, 1, 1)
        self._enum_start = Gtk.SpinButton.new_with_range(0, 9999, 1)
        self._enum_start.set_value(1)
        self._enum_start.connect("value-changed", lambda *a: self._schedule_preview())
        enum_grid.attach(self._enum_start, 1, 0, 1, 1)

        enum_grid.attach(Gtk.Label(label="Pad digits:", xalign=0), 0, 1, 1, 1)
        self._enum_pad = Gtk.SpinButton.new_with_range(0, 10, 1)
        self._enum_pad.set_value(0)
        self._enum_pad.connect("value-changed", lambda *a: self._schedule_preview())
        enum_grid.attach(self._enum_pad, 1, 1, 1, 1)

        enum_grid.attach(Gtk.Label(label="Separator:", xalign=0), 0, 2, 1, 1)
        self._enum_sep = Gtk.Entry()
        self._enum_sep.set_text("_")
        self._enum_sep.set_max_length(4)
        self._enum_sep.connect("changed", lambda *a: self._schedule_preview())
        enum_grid.attach(self._enum_sep, 1, 2, 1, 1)

        return scroll

    def _make_file_list(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Column header box
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_border_width(4)
        lbl_orig = Gtk.Label(label="Original Name", xalign=0)
        lbl_orig.set_markup("<b>Original Name</b>")
        lbl_new = Gtk.Label(label="New Name", xalign=0)
        lbl_new.set_markup("<b>New Name</b>")
        header.pack_start(lbl_orig, True, True, 4)
        header.pack_start(lbl_new, True, True, 4)
        box.pack_start(header, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 0)

        # List store: original, new_name, status, changed, error
        self._store = Gtk.ListStore(str, str, str, bool, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(False)

        renderer_orig = Gtk.CellRendererText()
        renderer_orig.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        col_orig = Gtk.TreeViewColumn("Original", renderer_orig, text=COL_ORIGINAL)
        col_orig.set_expand(True)
        self._tree.append_column(col_orig)

        renderer_new = Gtk.CellRendererText()
        renderer_new.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        col_new = Gtk.TreeViewColumn("New", renderer_new, text=COL_NEW_NAME)
        col_new.set_cell_data_func(renderer_new, self._cell_color_func)
        col_new.set_expand(True)
        self._tree.append_column(col_new)

        renderer_status = Gtk.CellRendererText()
        col_status = Gtk.TreeViewColumn("", renderer_status, text=COL_STATUS)
        col_status.set_fixed_width(30)
        self._tree.append_column(col_status)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        # Drop target
        self._tree.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-received", self._on_drag_data)

        return box

    # ── Helpers ──────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_margin_top(8)
        return lbl

    def _cell_color_func(self, col, renderer, model, it, data):
        changed = model.get_value(it, COL_CHANGED)
        error = model.get_value(it, COL_ERROR)
        if error:
            renderer.set_property("foreground", "red")
        elif changed:
            renderer.set_property("foreground", "#2ecc71")
        else:
            renderer.set_property("foreground", None)

    def _build_engine(self) -> PowerRenameEngine:
        return PowerRenameEngine(
            search=self._search_entry.get_text(),
            replace=self._replace_entry.get_text(),
            use_regex=self._regex_check.get_active(),
            case_sensitive=self._case_check.get_active(),
            case_transform=self._case_combo.get_active_text(),
            apply_to_extension=self._ext_check.get_active(),
            enumerate_files=self._enum_check.get_active(),
            enum_start=int(self._enum_start.get_value()),
            enum_padding=int(self._enum_pad.get_value()),
            enum_separator=self._enum_sep.get_text(),
        )

    # ── Preview ──────────────────────────────────────────────────────────

    def _schedule_preview(self):
        """Debounce: schedule preview after a short delay."""
        self._preview_id += 1
        pid = self._preview_id
        GLib.timeout_add(150, lambda: self._update_preview() if pid == self._preview_id else None)

    def _update_preview(self):
        engine = self._build_engine()
        results = engine.preview(self._paths)
        self._store.clear()

        changed_count = 0
        error_count = 0
        for r in results:
            status = "✓" if r.success else "✗"
            if not r.success:
                error_count += 1
            elif r.changed:
                changed_count += 1
            self._store.append([
                r.original.name,
                r.new_name if r.success else f"Error: {r.error}",
                status,
                r.changed and r.success,
                r.error or "",
            ])

        msg = f"{len(self._paths)} file(s) loaded  •  {changed_count} will be renamed"
        if error_count:
            msg += f"  •  {error_count} error(s)"
        ctx = self._status_bar.get_context_id("preview")
        self._status_bar.pop(ctx)
        self._status_bar.push(ctx, msg)

    # ── Signal handlers ──────────────────────────────────────────────────

    def _on_add_files(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Files", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK:
            for f in dialog.get_filenames():
                p = Path(f)
                if p not in self._paths:
                    self._paths.append(p)
            self._update_preview()
        dialog.destroy()

    def _on_add_folder(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Folder", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        if dialog.run() == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            recursive = self._recursive_check.get_active()
            engine = self._build_engine()
            new_paths = engine.scan_directory(folder, recursive=recursive)
            for p in new_paths:
                if p not in self._paths:
                    self._paths.append(p)
            self._update_preview()
        dialog.destroy()

    def _on_clear_list(self, button):
        self._paths.clear()
        self._store.clear()

    def _on_enum_toggle(self, button):
        self._enum_frame.set_sensitive(button.get_active())
        self._schedule_preview()

    def _on_drag_data(self, widget, context, x, y, data, info, time):
        uris = data.get_uris()
        for uri in uris:
            path = GLib.filename_from_uri(uri)[0]
            p = Path(path)
            if p.is_file() and p not in self._paths:
                self._paths.append(p)
            elif p.is_dir():
                engine = self._build_engine()
                for fp in engine.scan_directory(str(p)):
                    if fp not in self._paths:
                        self._paths.append(fp)
        self._update_preview()
        Gtk.drag_finish(context, True, False, time)

    def _on_rename(self, button):
        engine = self._build_engine()
        results = engine.apply(self._paths)

        success = sum(1 for r in results if r.changed and r.success)
        errors = sum(1 for r in results if not r.success)

        # Update paths to reflect renames
        self._paths = [r.new_path if (r.changed and r.success) else r.original for r in results]
        self._update_preview()

        msg = Gtk.MessageDialog(
            parent=self, flags=0,
            message_type=Gtk.MessageType.INFO if errors == 0 else Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=f"Rename complete",
        )
        msg.format_secondary_text(f"Renamed: {success}  •  Errors: {errors}")
        msg.run()
        msg.destroy()
