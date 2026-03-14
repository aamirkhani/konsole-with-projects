"""Peek GTK3 window - quick file preview."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from pathlib import Path
from .engine import PeekEngine, FileInfo


class _TextPreview(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self._view = Gtk.TextView()
        self._view.set_editable(False)
        self._view.set_monospace(True)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.add(self._view)

    def set_content(self, text: str):
        self._view.get_buffer().set_text(text)


class _ImagePreview(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._image = Gtk.Image()
        sw = Gtk.ScrolledWindow()
        sw.add(self._image)
        self.pack_start(sw, True, True, 0)
        self._size_lbl = Gtk.Label()
        self._size_lbl.get_style_context().add_class("dim-label")
        self.pack_start(self._size_lbl, False, False, 0)

    def set_file(self, path: Path, max_w: int = 800, max_h: int = 600):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
            orig_w, orig_h = pb.get_width(), pb.get_height()
            scale = min(max_w / orig_w, max_h / orig_h, 1.0)
            if scale < 1.0:
                pb = pb.scale_simple(
                    int(orig_w * scale), int(orig_h * scale),
                    GdkPixbuf.InterpType.BILINEAR
                )
            self._image.set_from_pixbuf(pb)
            self._size_lbl.set_text(f"{orig_w} × {orig_h} pixels")
        except Exception as e:
            self._image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
            self._size_lbl.set_text(f"Cannot load image: {e}")


class _BinaryPreview(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self._view = Gtk.TextView()
        self._view.set_editable(False)
        self._view.set_monospace(True)
        self.add(self._view)

    def set_file(self, path: Path):
        try:
            with open(path, "rb") as f:
                data = f.read(512)
            lines = []
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"{i:08x}  {hex_part:<48}  {asc_part}")
            self._view.get_buffer().set_text("\n".join(lines))
        except Exception as e:
            self._view.get_buffer().set_text(f"Cannot read file: {e}")


class PeekWindow(Gtk.Window):
    def __init__(self, path: Path = None, parent=None):
        super().__init__(title="Peek")
        self.set_default_size(780, 580)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = PeekEngine()
        self._current_path: Path = path
        self._build_ui()

        if path:
            self._load_file(path)

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Toolbar
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(8)

        btn_open = Gtk.Button(label="Open File…")
        btn_open.connect("clicked", self._on_open_file)
        bar.pack_start(btn_open, False, False, 0)

        self._path_lbl = Gtk.Label(label="No file selected", xalign=0)
        self._path_lbl.get_style_context().add_class("dim-label")
        self._path_lbl.set_ellipsize(3)
        bar.pack_start(self._path_lbl, True, True, 0)

        self._open_ext_btn = Gtk.Button(label="Open with Default App")
        self._open_ext_btn.connect("clicked", self._on_open_external)
        self._open_ext_btn.set_sensitive(False)
        bar.pack_start(self._open_ext_btn, False, False, 0)

        vbox.pack_start(bar, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # File info strip
        info_box = Gtk.Box(spacing=16)
        info_box.set_border_width(8)
        self._type_icon = Gtk.Image.new_from_icon_name("text-x-generic", Gtk.IconSize.LARGE_TOOLBAR)
        info_box.pack_start(self._type_icon, False, False, 0)
        self._info_lbl = Gtk.Label(label="", xalign=0)
        info_box.pack_start(self._info_lbl, True, True, 0)
        vbox.pack_start(info_box, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Preview stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        self._text_preview = _TextPreview()
        self._stack.add_named(self._text_preview, "text")

        self._image_preview = _ImagePreview()
        self._stack.add_named(self._image_preview, "image")

        self._binary_preview = _BinaryPreview()
        self._stack.add_named(self._binary_preview, "binary")

        # Placeholder
        placeholder = Gtk.Label(label="Open a file to preview it here")
        placeholder.get_style_context().add_class("dim-label")
        self._stack.add_named(placeholder, "placeholder")
        self._stack.set_visible_child_name("placeholder")

        vbox.pack_start(self._stack, True, True, 0)

        # Status bar
        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

        # Drag & drop for files
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY
        )
        self.connect("drag-data-received", self._on_drag_data)

    def _on_open_file(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Open File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        if dialog.run() == Gtk.ResponseType.OK:
            path = Path(dialog.get_filename())
            self._load_file(path)
        dialog.destroy()

    def _on_open_external(self, btn):
        if self._current_path:
            self._engine.open_with_default(self._current_path)

    def _on_drag_data(self, widget, ctx, x, y, data, info, time):
        uris = data.get_uris()
        if uris:
            from urllib.parse import urlparse, unquote
            path = Path(unquote(urlparse(uris[0]).path))
            self._load_file(path)

    def _load_file(self, path: Path):
        self._current_path = path
        self.set_title(f"Peek — {path.name}")
        self._path_lbl.set_text(str(path))
        self._open_ext_btn.set_sensitive(True)

        info = self._engine.get_file_info(path)

        # Update icon
        icon_map = {
            "text": "text-x-generic",
            "image": "image-x-generic",
            "pdf": "application-pdf",
            "video": "video-x-generic",
            "audio": "audio-x-generic",
            "archive": "package-x-generic",
            "binary": "application-octet-stream",
        }
        self._type_icon.set_from_icon_name(
            icon_map.get(info.category, "text-x-generic"),
            Gtk.IconSize.LARGE_TOOLBAR
        )

        self._info_lbl.set_markup(
            f"<b>{info.name}</b>  •  {info.size_str}  •  {info.mime_type}"
        )

        # Show appropriate preview
        if info.category == "text":
            content = self._engine.get_text_content(path)
            self._text_preview.set_content(content)
            self._stack.set_visible_child_name("text")
        elif info.category == "image":
            self._image_preview.set_file(path)
            self._stack.set_visible_child_name("image")
        elif info.category == "archive":
            listing = self._engine.get_archive_listing(path)
            self._text_preview.set_content(listing)
            self._stack.set_visible_child_name("text")
        elif info.category == "binary":
            self._binary_preview.set_file(path)
            self._stack.set_visible_child_name("binary")
        else:
            self._text_preview.set_content(
                f"Preview not available for {info.mime_type}\nSize: {info.size_str}"
            )
            self._stack.set_visible_child_name("text")

        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, f"{info.category.capitalize()} file  •  {info.size_str}")


class PeekSettingsWindow(Gtk.Window):
    """Launcher / settings window for Peek."""

    def __init__(self, parent=None):
        super().__init__(title="Peek — Quick File Preview")
        self.set_default_size(480, 300)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = PeekEngine()
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        header = Gtk.Box(spacing=12)
        header.set_border_width(16)
        icon = Gtk.Image.new_from_icon_name("document-preview", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        header.pack_start(icon, False, False, 0)
        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>Peek</big></b>")
        hbox.pack_start(title, False, False, 0)
        sub = Gtk.Label(
            label="Quick file previewer supporting text, images, archives and more.",
            xalign=0
        )
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("dim-label")
        hbox.pack_start(sub, False, False, 0)
        header.pack_start(hbox, True, True, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        grid = Gtk.Grid(row_spacing=10, column_spacing=16)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="Wrap text:", xalign=0), 0, 0, 1, 1)
        self._wrap_check = Gtk.CheckButton()
        self._wrap_check.set_active(self._engine.wrap_text)
        grid.attach(self._wrap_check, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Max preview size (KB):", xalign=0), 0, 1, 1, 1)
        self._max_spin = Gtk.SpinButton.new_with_range(8, 4096, 8)
        self._max_spin.set_value(self._engine.max_preview_bytes // 1024)
        grid.attach(self._max_spin, 1, 1, 1, 1)

        vbox.pack_start(grid, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        btn_bar = Gtk.Box(spacing=8)
        btn_bar.set_border_width(12)

        btn_open = Gtk.Button(label="Open Peek Preview…")
        btn_open.get_style_context().add_class("suggested-action")
        btn_open.connect("clicked", self._on_open_peek)
        btn_bar.pack_start(btn_open, False, False, 0)

        vbox.pack_start(btn_bar, False, False, 0)
        self.show_all()

    def _on_open_peek(self, btn):
        self._engine.wrap_text = self._wrap_check.get_active()
        self._engine.max_preview_bytes = int(self._max_spin.get_value()) * 1024
        win = PeekWindow(parent=self)
        win.show_all()
