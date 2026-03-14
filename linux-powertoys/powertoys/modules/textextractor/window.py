"""TextExtractor GTK3 window - full OCR UI."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import os
import threading
from pathlib import Path
from .extractor import TextExtractorEngine


class TextExtractorWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Text Extractor")
        self.set_default_size(700, 500)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = TextExtractorEngine()
        self._image_path = None

        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        if not self._engine._has_tesseract:
            self._show_install_bar(vbox)

        paned = Gtk.Paned()
        paned.set_position(350)
        vbox.pack_start(paned, True, True, 0)

        paned.add1(self._build_image_panel())
        paned.add2(self._build_text_panel())

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

    def _show_install_bar(self, parent):
        info = Gtk.InfoBar()
        info.set_message_type(Gtk.MessageType.WARNING)
        lbl = Gtk.Label(label="tesseract-ocr is not installed. Install with: sudo apt install tesseract-ocr")
        info.get_content_area().add(lbl)
        parent.pack_start(info, False, False, 0)

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        btn_open = Gtk.Button(label="Open Image")
        btn_open.connect("clicked", self._on_open_image)
        bar.pack_start(btn_open, False, False, 0)

        btn_screenshot = Gtk.Button(label="Capture Screenshot")
        btn_screenshot.connect("clicked", self._on_screenshot)
        bar.pack_start(btn_screenshot, False, False, 0)

        btn_clipboard = Gtk.Button(label="OCR Clipboard")
        btn_clipboard.connect("clicked", self._on_ocr_clipboard)
        bar.pack_start(btn_clipboard, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_extract = Gtk.Button(label="Extract Text")
        btn_extract.get_style_context().add_class("suggested-action")
        btn_extract.connect("clicked", self._on_extract)
        bar.pack_start(btn_extract, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        # Language
        bar.pack_start(Gtk.Label(label="Language:"), False, False, 0)
        self._lang_combo = Gtk.ComboBoxText()
        langs = self._engine.get_available_languages()
        for lang in langs:
            self._lang_combo.append_text(lang)
        self._lang_combo.set_active(0)
        self._lang_combo.connect("changed", self._on_lang_changed)
        bar.pack_start(self._lang_combo, False, False, 0)

        return bar

    def _build_image_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Source Image</b>")
        lbl.set_border_width(4)
        box.pack_start(lbl, False, False, 0)

        self._image_view = Gtk.Image()
        self._image_view.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)

        scroll = Gtk.ScrolledWindow()
        viewport = Gtk.Viewport()
        viewport.add(self._image_view)
        scroll.add(viewport)

        # Drop target
        scroll.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        scroll.connect("drag-data-received", self._on_drag)

        box.pack_start(scroll, True, True, 0)

        self._img_info = Gtk.Label(label="Drop an image here or click Open Image", xalign=0)
        self._img_info.set_border_width(4)
        box.pack_start(self._img_info, False, False, 0)

        return box

    def _build_text_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Box(spacing=6)
        header.set_border_width(4)
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Extracted Text</b>")
        header.pack_start(lbl, True, True, 0)

        btn_copy = Gtk.Button(label="Copy All")
        btn_copy.connect("clicked", self._on_copy_all)
        header.pack_start(btn_copy, False, False, 0)

        btn_clear = Gtk.Button(label="Clear")
        btn_clear.connect("clicked", lambda *a: self._text_buffer.set_text(""))
        header.pack_start(btn_clear, False, False, 0)

        box.pack_start(header, False, False, 0)

        self._text_buffer = Gtk.TextBuffer()
        text_view = Gtk.TextView(buffer=self._text_buffer)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.set_left_margin(8)
        text_view.set_right_margin(8)

        scroll = Gtk.ScrolledWindow()
        scroll.add(text_view)
        box.pack_start(scroll, True, True, 0)

        # Search in text
        search_box = Gtk.SearchBar()
        self._text_search = Gtk.SearchEntry()
        self._text_search.connect("search-changed", self._on_search_text)
        search_box.add(self._text_search)
        box.pack_start(search_box, False, False, 0)

        self._spinner = Gtk.Spinner()
        self._spinner.set_no_show_all(True)
        box.pack_start(self._spinner, False, False, 0)

        return box

    def _load_image(self, path: str):
        self._image_path = path
        try:
            from gi.repository import GdkPixbuf
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 320, 400, True)
            self._image_view.set_from_pixbuf(pixbuf)
            stat = Path(path).stat()
            self._img_info.set_text(f"{Path(path).name}  •  {stat.st_size // 1024} KB")
        except Exception as e:
            self._img_info.set_text(f"Error loading image: {e}")

    def _extract_text(self, image_path: str):
        self._spinner.show()
        self._spinner.start()

        def run():
            self._engine.language = self._lang_combo.get_active_text() or "eng"
            text = self._engine.ocr_file(image_path)
            GLib.idle_add(self._on_text_ready, text)

        threading.Thread(target=run, daemon=True).start()

    def _on_text_ready(self, text: str):
        self._spinner.stop()
        self._spinner.hide()
        self._text_buffer.set_text(text)
        words = len(text.split())
        chars = len(text)
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, f"Extracted: {words} words, {chars} characters")

    def _on_open_image(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Open Image", parent=self, action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        f = Gtk.FileFilter()
        f.set_name("Images")
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff", "*.gif", "*.webp"]:
            f.add_pattern(ext)
        dialog.add_filter(f)
        if dialog.run() == Gtk.ResponseType.OK:
            self._load_image(dialog.get_filename())
        dialog.destroy()

    def _on_screenshot(self, btn):
        self.hide()
        GLib.timeout_add(500, self._do_screenshot)

    def _do_screenshot(self):
        path = self._engine.capture_full_screenshot()
        self.show()
        if path:
            self._load_image(path)
            ctx = self._status.get_context_id("main")
            self._status.push(ctx, "Screenshot captured")
        else:
            ctx = self._status.get_context_id("main")
            self._status.push(ctx, "Screenshot failed. Install scrot: sudo apt install scrot")
        return False

    def _on_extract(self, btn):
        if not self._image_path:
            ctx = self._status.get_context_id("main")
            self._status.push(ctx, "No image loaded")
            return
        self._extract_text(self._image_path)

    def _on_ocr_clipboard(self, btn):
        def run():
            text = self._engine.ocr_clipboard_image()
            GLib.idle_add(self._on_text_ready, text)
        threading.Thread(target=run, daemon=True).start()

    def _on_drag(self, widget, ctx, x, y, data, info, time):
        for uri in data.get_uris():
            path = GLib.filename_from_uri(uri)[0]
            if Path(path).is_file():
                self._load_image(path)
                break
        Gtk.drag_finish(ctx, True, False, time)

    def _on_lang_changed(self, combo):
        self._engine.language = combo.get_active_text() or "eng"

    def _on_copy_all(self, btn):
        text = self._text_buffer.get_text(
            self._text_buffer.get_start_iter(),
            self._text_buffer.get_end_iter(),
            True,
        )
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(text, -1)

    def _on_search_text(self, entry):
        query = entry.get_text()
        if not query:
            return
        start = self._text_buffer.get_start_iter()
        found = start.forward_search(query, 0, None)
        if found:
            match_start, match_end = found
            self._text_buffer.select_range(match_start, match_end)
