"""ImageResizer GTK3 window - full UI for batch image resizing."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

import threading
from pathlib import Path
from typing import List

from .engine import (
    ImageResizerEngine, ResizePreset, ResizeResult,
    DEFAULT_PRESETS, FIT_MODES, SUPPORTED_FORMATS, HAS_PILLOW
)

COL_FILENAME = 0
COL_ORIG_SIZE = 1
COL_NEW_SIZE = 2
COL_STATUS = 3
COL_PATH = 4


class ImageResizerWindow(Gtk.Window):
    def __init__(self, paths: List[str] = None, parent=None):
        super().__init__(title="Image Resizer")
        self.set_default_size(950, 620)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._paths: List[Path] = []
        self._presets = DEFAULT_PRESETS[:]
        self._resizing = False

        self._build_ui()

        if paths:
            for p in paths:
                self._add_path(Path(p))
            self._refresh_list()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        paned = Gtk.Paned()
        paned.set_position(350)
        vbox.pack_start(paned, True, True, 0)

        paned.add1(self._build_settings_panel())
        paned.add2(self._build_file_panel())

        self._progress = Gtk.ProgressBar()
        self._progress.set_no_show_all(True)
        vbox.pack_start(self._progress, False, False, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        if not HAS_PILLOW:
            self._warn("Pillow is not installed. Image resizing unavailable. Install with: pip3 install Pillow")

        self.show_all()

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        btn = Gtk.Button(label="Add Images")
        btn.connect("clicked", self._on_add_images)
        bar.pack_start(btn, False, False, 0)

        btn2 = Gtk.Button(label="Add Folder")
        btn2.connect("clicked", self._on_add_folder)
        bar.pack_start(btn2, False, False, 0)

        btn3 = Gtk.Button(label="Clear")
        btn3.connect("clicked", lambda *a: self._clear())
        bar.pack_start(btn3, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self._btn_resize = Gtk.Button(label="Resize All")
        self._btn_resize.get_style_context().add_class("suggested-action")
        self._btn_resize.connect("clicked", self._on_resize)
        bar.pack_start(self._btn_resize, False, False, 0)

        return bar

    def _build_settings_panel(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        grid.set_border_width(12)
        scroll.add(grid)

        row = 0

        # ── Presets ───────────────────────────────────────────────────────
        grid.attach(self._section("Presets"), 0, row, 2, 1); row += 1
        self._preset_combo = Gtk.ComboBoxText()
        self._preset_combo.append_text("Custom")
        for p in self._presets:
            self._preset_combo.append_text(str(p))
        self._preset_combo.set_active(2)  # Medium
        self._preset_combo.connect("changed", self._on_preset_changed)
        grid.attach(self._preset_combo, 0, row, 2, 1); row += 1

        # ── Custom Size ────────────────────────────────────────────────────
        self._custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        grid.attach(self._custom_box, 0, row, 2, 1); row += 1

        size_grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        self._custom_box.pack_start(size_grid, False, False, 0)

        size_grid.attach(Gtk.Label(label="Width (px):", xalign=0), 0, 0, 1, 1)
        self._width_spin = Gtk.SpinButton.new_with_range(1, 99999, 1)
        self._width_spin.set_value(1920)
        size_grid.attach(self._width_spin, 1, 0, 1, 1)

        size_grid.attach(Gtk.Label(label="Height (px):", xalign=0), 0, 1, 1, 1)
        self._height_spin = Gtk.SpinButton.new_with_range(1, 99999, 1)
        self._height_spin.set_value(1080)
        size_grid.attach(self._height_spin, 1, 1, 1, 1)

        size_grid.attach(Gtk.Label(label="Fit mode:", xalign=0), 0, 2, 1, 1)
        self._fit_combo = Gtk.ComboBoxText()
        for m in FIT_MODES:
            self._fit_combo.append_text(m)
        self._fit_combo.set_active(0)
        size_grid.attach(self._fit_combo, 1, 2, 1, 1)

        self._custom_box.set_sensitive(False)  # preset selected initially

        # ── Output ────────────────────────────────────────────────────────
        grid.attach(self._section("Output"), 0, row, 2, 1); row += 1

        grid.attach(Gtk.Label(label="Suffix:", xalign=0), 0, row, 1, 1)
        self._suffix_entry = Gtk.Entry()
        self._suffix_entry.set_text("_resized")
        grid.attach(self._suffix_entry, 1, row, 1, 1); row += 1

        grid.attach(Gtk.Label(label="Format:", xalign=0), 0, row, 1, 1)
        self._format_combo = Gtk.ComboBoxText()
        for fmt in ["Same as source", "JPEG", "PNG", "WebP"]:
            self._format_combo.append_text(fmt)
        self._format_combo.set_active(0)
        grid.attach(self._format_combo, 1, row, 1, 1); row += 1

        grid.attach(Gtk.Label(label="JPEG quality:", xalign=0), 0, row, 1, 1)
        self._quality_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self._quality_spin.set_value(90)
        grid.attach(self._quality_spin, 1, row, 1, 1); row += 1

        grid.attach(Gtk.Label(label="Output folder:", xalign=0), 0, row, 1, 1)
        self._outdir_btn = Gtk.FileChooserButton(title="Choose output folder", action=Gtk.FileChooserAction.SELECT_FOLDER)
        grid.attach(self._outdir_btn, 1, row, 1, 1); row += 1

        # ── Options ──────────────────────────────────────────────────────
        grid.attach(self._section("Options"), 0, row, 2, 1); row += 1
        self._keep_orig = Gtk.CheckButton(label="Keep original files")
        self._keep_orig.set_active(True)
        grid.attach(self._keep_orig, 0, row, 2, 1); row += 1
        self._sharpen = Gtk.CheckButton(label="Apply sharpening after resize")
        grid.attach(self._sharpen, 0, row, 2, 1); row += 1

        return scroll

    def _build_file_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # List store
        self._store = Gtk.ListStore(str, str, str, str, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)

        for i, (title, col_id) in enumerate([
            ("Filename", COL_FILENAME),
            ("Original", COL_ORIG_SIZE),
            ("New Size", COL_NEW_SIZE),
            ("Status", COL_STATUS),
        ]):
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            if col_id == COL_FILENAME:
                col.set_expand(True)
            self._tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        # Drag & drop
        self._tree.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-received", self._on_drag)

        return box

    # ── Helpers ────────────────────────────────────────────────────────────

    def _section(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_margin_top(8)
        return lbl

    def _add_path(self, p: Path):
        if p.suffix.lower() in SUPPORTED_FORMATS and p not in self._paths:
            self._paths.append(p)

    def _clear(self):
        self._paths.clear()
        self._store.clear()
        self._set_status("Ready")

    def _refresh_list(self):
        self._store.clear()
        for p in self._paths:
            try:
                from PIL import Image
                with Image.open(p) as img:
                    w, h = img.size
                    orig = f"{w}×{h}"
            except Exception:
                orig = "?"
            self._store.append([p.name, orig, "—", "Pending", str(p)])
        self._set_status(f"{len(self._paths)} image(s) loaded")

    def _build_engine(self) -> ImageResizerEngine:
        preset_idx = self._preset_combo.get_active()
        preset = None if preset_idx == 0 else self._presets[preset_idx - 1]

        fmt_map = {"Same as source": "same", "JPEG": "jpg", "PNG": "png", "WebP": "webp"}
        fmt = fmt_map.get(self._format_combo.get_active_text(), "same")

        out_folder = self._outdir_btn.get_filename()
        return ImageResizerEngine(
            preset=preset,
            custom_width=int(self._width_spin.get_value()),
            custom_height=int(self._height_spin.get_value()),
            fit_mode=self._fit_combo.get_active_text(),
            output_suffix=self._suffix_entry.get_text() or "_resized",
            output_dir=out_folder,
            output_format=fmt,
            quality=int(self._quality_spin.get_value()),
            keep_originals=self._keep_orig.get_active(),
            sharpen=self._sharpen.get_active(),
        )

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)

    def _warn(self, msg: str):
        bar = Gtk.InfoBar()
        bar.set_message_type(Gtk.MessageType.WARNING)
        bar.get_content_area().add(Gtk.Label(label=msg))
        bar.show_all()
        self.get_child().pack_start(bar, False, False, 0)
        self.get_child().reorder_child(bar, 1)

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_preset_changed(self, combo):
        self._custom_box.set_sensitive(combo.get_active() == 0)

    def _on_add_images(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Add Images", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        f = Gtk.FileFilter()
        f.set_name("Images")
        for ext in SUPPORTED_FORMATS:
            f.add_pattern(f"*{ext}")
        dialog.add_filter(f)
        if dialog.run() == Gtk.ResponseType.OK:
            for fn in dialog.get_filenames():
                self._add_path(Path(fn))
            self._refresh_list()
        dialog.destroy()

    def _on_add_folder(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Add Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            folder = Path(dialog.get_filename())
            for ext in SUPPORTED_FORMATS:
                for p in folder.glob(f"*{ext}"):
                    self._add_path(p)
            self._refresh_list()
        dialog.destroy()

    def _on_drag(self, widget, ctx, x, y, data, info, time):
        for uri in data.get_uris():
            path = GLib.filename_from_uri(uri)[0]
            p = Path(path)
            if p.is_file():
                self._add_path(p)
            elif p.is_dir():
                for ext in SUPPORTED_FORMATS:
                    for sub in p.glob(f"*{ext}"):
                        self._add_path(sub)
        self._refresh_list()
        Gtk.drag_finish(ctx, True, False, time)

    def _on_resize(self, btn):
        if self._resizing or not self._paths:
            return
        self._resizing = True
        self._btn_resize.set_sensitive(False)
        self._progress.show()
        self._progress.set_fraction(0)

        engine = self._build_engine()
        paths = self._paths[:]

        def run():
            results = []
            def cb(done, total, result):
                frac = done / total
                GLib.idle_add(self._on_progress, frac, done, total, result, results)
            engine.resize_batch(paths, progress_cb=cb)

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, frac, done, total, result, results):
        results.append(result)
        self._progress.set_fraction(frac)
        # Update row
        it = self._store.get_iter_first()
        count = 0
        while it:
            if self._store.get_value(it, COL_PATH) == str(result.source):
                new_sz = f"{result.new_size[0]}×{result.new_size[1]}" if result.success else "—"
                status = "✓ Done" if result.success else f"✗ {result.error}"
                self._store.set_value(it, COL_NEW_SIZE, new_sz)
                self._store.set_value(it, COL_STATUS, status)
                break
            it = self._store.iter_next(it)

        if done == total:
            self._progress.hide()
            self._btn_resize.set_sensitive(True)
            self._resizing = False
            success = sum(1 for r in results if r.success)
            self._set_status(f"Done: {success}/{total} resized successfully")
