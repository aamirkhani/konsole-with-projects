"""PasteAsPlainText GTK3 window."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .engine import PastePlainEngine


class PastePlainWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Paste As Plain Text")
        self.set_default_size(600, 500)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = PastePlainEngine()
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Header
        header = Gtk.Box(spacing=12)
        header.set_border_width(16)
        icon = Gtk.Image.new_from_icon_name("edit-paste", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        header.pack_start(icon, False, False, 0)

        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>Paste As Plain Text</big></b>")
        hbox.pack_start(title, False, False, 0)
        sub = Gtk.Label(
            label="Strip HTML, Markdown, and other formatting from clipboard content.",
            xalign=0
        )
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("dim-label")
        hbox.pack_start(sub, False, False, 0)
        header.pack_start(hbox, True, True, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Options
        opts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        opts.set_border_width(12)

        self._html_check = Gtk.CheckButton(label="Strip HTML tags")
        self._html_check.set_active(self._engine.strip_html_tags)
        self._html_check.connect("toggled", self._on_options_changed)
        opts.pack_start(self._html_check, False, False, 0)

        self._md_check = Gtk.CheckButton(label="Strip Markdown formatting")
        self._md_check.set_active(self._engine.strip_markdown_syntax)
        self._md_check.connect("toggled", self._on_options_changed)
        opts.pack_start(self._md_check, False, False, 0)

        self._blank_check = Gtk.CheckButton(label="Collapse multiple blank lines")
        self._blank_check.set_active(self._engine.collapse_blank_lines)
        self._blank_check.connect("toggled", self._on_options_changed)
        opts.pack_start(self._blank_check, False, False, 0)

        self._trim_check = Gtk.CheckButton(label="Trim leading/trailing whitespace")
        self._trim_check.set_active(self._engine.trim_whitespace)
        self._trim_check.connect("toggled", self._on_options_changed)
        opts.pack_start(self._trim_check, False, False, 0)

        vbox.pack_start(opts, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Preview area
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_border_width(8)

        # Original
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left_lbl = Gtk.Label(xalign=0)
        left_lbl.set_markup("<b>Original (from clipboard)</b>")
        left_box.pack_start(left_lbl, False, False, 0)
        scroll_l = Gtk.ScrolledWindow()
        self._orig_view = Gtk.TextView()
        self._orig_view.set_editable(False)
        self._orig_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scroll_l.add(self._orig_view)
        left_box.pack_start(scroll_l, True, True, 0)
        paned.pack1(left_box, True, True)

        # Stripped
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_lbl = Gtk.Label(xalign=0)
        right_lbl.set_markup("<b>Stripped (plain text)</b>")
        right_box.pack_start(right_lbl, False, False, 0)
        scroll_r = Gtk.ScrolledWindow()
        self._strip_view = Gtk.TextView()
        self._strip_view.set_editable(False)
        self._strip_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scroll_r.add(self._strip_view)
        right_box.pack_start(scroll_r, True, True, 0)
        paned.pack2(right_box, True, True)

        vbox.pack_start(paned, True, True, 0)

        # Button bar
        btn_bar = Gtk.Box(spacing=8)
        btn_bar.set_border_width(12)

        btn_preview = Gtk.Button(label="Preview Clipboard")
        btn_preview.connect("clicked", self._on_preview)
        btn_bar.pack_start(btn_preview, False, False, 0)

        btn_apply = Gtk.Button(label="Strip & Replace Clipboard")
        btn_apply.get_style_context().add_class("suggested-action")
        btn_apply.connect("clicked", self._on_apply)
        btn_bar.pack_start(btn_apply, False, False, 0)

        self._status_lbl = Gtk.Label(label="")
        self._status_lbl.get_style_context().add_class("dim-label")
        btn_bar.pack_start(self._status_lbl, False, False, 8)

        vbox.pack_start(btn_bar, False, False, 0)

        self.show_all()

    def _on_options_changed(self, *args):
        self._engine.strip_html_tags = self._html_check.get_active()
        self._engine.strip_markdown_syntax = self._md_check.get_active()
        self._engine.collapse_blank_lines = self._blank_check.get_active()
        self._engine.trim_whitespace = self._trim_check.get_active()
        # Re-run preview if we have content
        orig_text = self._orig_view.get_buffer().get_text(
            self._orig_view.get_buffer().get_start_iter(),
            self._orig_view.get_buffer().get_end_iter(),
            False
        )
        if orig_text:
            stripped = self._engine.process(orig_text)
            self._strip_view.get_buffer().set_text(stripped)

    def _on_preview(self, btn):
        result = self._engine.get_and_strip()
        if result is None:
            self._status_lbl.set_text("Clipboard is empty or could not be read")
            return
        original, stripped = result
        self._orig_view.get_buffer().set_text(original)
        self._strip_view.get_buffer().set_text(stripped)
        orig_len = len(original)
        strip_len = len(stripped)
        saved = orig_len - strip_len
        self._status_lbl.set_text(
            f"Original: {orig_len} chars  →  Stripped: {strip_len} chars  ({saved:+d} chars)"
        )

    def _on_apply(self, btn):
        ok = self._engine.paste_plain()
        if ok:
            self._status_lbl.set_markup("<span color='green'>Clipboard updated with plain text</span>")
            self._on_preview(btn)
        else:
            self._status_lbl.set_text("Failed to write clipboard (xclip/xsel required)")
