"""ColorPicker GTK3 window - full UI for screen color picking."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from .picker import ColorPickerEngine


class ColorPickerWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Color Picker")
        self.set_default_size(480, 540)
        self.set_resizable(False)
        if parent:
            self.set_transient_for(parent)

        self._engine = ColorPickerEngine()
        self._r, self._g, self._b = 30, 144, 255  # default: dodger blue
        self._history = []  # list of (r, g, b)

        self._build_ui()
        self._update_display()

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Color preview area
        self._preview = Gtk.DrawingArea()
        self._preview.set_size_request(-1, 120)
        self._preview.connect("draw", self._on_draw_preview)
        vbox.pack_start(self._preview, False, False, 0)

        # Main content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(12)
        vbox.pack_start(content, True, True, 0)

        # RGB Sliders
        content.pack_start(self._section("Color Channels"), False, False, 0)

        slider_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        content.pack_start(slider_grid, False, False, 0)

        self._r_label = Gtk.Label(label="R", xalign=0)
        self._r_scale = self._make_channel_slider()
        self._r_scale.set_value(self._r)
        self._r_scale.connect("value-changed", self._on_rgb_changed)
        self._r_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
        self._r_spin.set_value(self._r)
        self._r_spin.connect("value-changed", self._on_spin_rgb)
        slider_grid.attach(self._r_label, 0, 0, 1, 1)
        slider_grid.attach(self._r_scale, 1, 0, 1, 1)
        slider_grid.attach(self._r_spin, 2, 0, 1, 1)

        self._g_label = Gtk.Label(label="G", xalign=0)
        self._g_scale = self._make_channel_slider()
        self._g_scale.set_value(self._g)
        self._g_scale.connect("value-changed", self._on_rgb_changed)
        self._g_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
        self._g_spin.set_value(self._g)
        self._g_spin.connect("value-changed", self._on_spin_rgb)
        slider_grid.attach(self._g_label, 0, 1, 1, 1)
        slider_grid.attach(self._g_scale, 1, 1, 1, 1)
        slider_grid.attach(self._g_spin, 2, 1, 1, 1)

        self._b_label = Gtk.Label(label="B", xalign=0)
        self._b_scale = self._make_channel_slider()
        self._b_scale.set_value(self._b)
        self._b_scale.connect("value-changed", self._on_rgb_changed)
        self._b_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
        self._b_spin.set_value(self._b)
        self._b_spin.connect("value-changed", self._on_spin_rgb)
        slider_grid.attach(self._b_label, 0, 2, 1, 1)
        slider_grid.attach(self._b_scale, 1, 2, 1, 1)
        slider_grid.attach(self._b_spin, 2, 2, 1, 1)

        # Hex input
        hex_box = Gtk.Box(spacing=8)
        content.pack_start(hex_box, False, False, 0)
        hex_box.pack_start(Gtk.Label(label="HEX:"), False, False, 0)
        self._hex_entry = Gtk.Entry()
        self._hex_entry.set_max_length(9)
        self._hex_entry.connect("activate", self._on_hex_entered)
        hex_box.pack_start(self._hex_entry, True, True, 0)
        btn_pick = Gtk.Button(label="Pick from Screen")
        btn_pick.connect("clicked", self._on_pick_screen)
        hex_box.pack_start(btn_pick, False, False, 0)

        # Format output
        content.pack_start(self._section("Color Values"), False, False, 0)

        self._format_store = Gtk.ListStore(str, str)  # format_name, value
        self._format_tree = Gtk.TreeView(model=self._format_store)
        self._format_tree.set_headers_visible(True)

        col_fmt = Gtk.TreeViewColumn("Format", Gtk.CellRendererText(), text=0)
        col_fmt.set_fixed_width(80)
        self._format_tree.append_column(col_fmt)

        rend_val = Gtk.CellRendererText()
        rend_val.set_property("family", "Monospace")
        col_val = Gtk.TreeViewColumn("Value", rend_val, text=1)
        col_val.set_expand(True)
        self._format_tree.append_column(col_val)

        self._format_tree.connect("row-activated", self._on_copy_format)

        fmt_scroll = Gtk.ScrolledWindow()
        fmt_scroll.set_min_content_height(150)
        fmt_scroll.add(self._format_tree)
        content.pack_start(fmt_scroll, True, True, 0)

        copy_hint = Gtk.Label(label="Double-click a row to copy value to clipboard")
        copy_hint.get_style_context().add_class("dim-label")
        content.pack_start(copy_hint, False, False, 0)

        # Color history
        content.pack_start(self._section("History"), False, False, 0)
        self._history_box = Gtk.FlowBox()
        self._history_box.set_max_children_per_line(12)
        self._history_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._history_box.connect("child-activated", self._on_history_click)
        content.pack_start(self._history_box, False, False, 0)

        # Action buttons
        btn_bar = Gtk.Box(spacing=6)
        content.pack_end(btn_bar, False, False, 0)

        btn_add_hist = Gtk.Button(label="Save to History")
        btn_add_hist.connect("clicked", lambda *a: self._save_to_history())
        btn_bar.pack_start(btn_add_hist, False, False, 0)

        self._btn_copy_hex = Gtk.Button(label="Copy HEX")
        self._btn_copy_hex.get_style_context().add_class("suggested-action")
        self._btn_copy_hex.connect("clicked", self._on_copy_hex)
        btn_bar.pack_end(self._btn_copy_hex, False, False, 0)

        self.show_all()

    def _make_channel_slider(self) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        return scale

    def _section(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_margin_top(8)
        return lbl

    # ── Update display ────────────────────────────────────────────────────

    def _update_display(self):
        r, g, b = self._r, self._g, self._b

        # Redraw preview
        self._preview.queue_draw()

        # Update hex
        self._hex_entry.set_text(self._engine.rgb_to_hex(r, g, b))

        # Update format table
        self._format_store.clear()
        for fmt in ColorPickerEngine.FORMATS:
            val = self._engine.format_color(r, g, b, fmt)
            self._format_store.append([fmt, val])

    def _on_draw_preview(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        r, g, b = self._r / 255, self._g / 255, self._b / 255
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Draw color text in contrasting color
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = 0.0 if lum > 0.5 else 1.0
        cr.set_source_rgb(text_color, text_color, text_color)
        cr.select_font_face("Monospace", 0, 0)
        cr.set_font_size(22)
        hex_text = self._engine.rgb_to_hex(self._r, self._g, self._b)
        _, _, tw, th, _, _ = cr.text_extents(hex_text)
        cr.move_to((w - tw) / 2, (h + th) / 2)
        cr.show_text(hex_text)

    # ── Signal handlers ───────────────────────────────────────────────────

    def _on_rgb_changed(self, scale):
        self._r = int(self._r_scale.get_value())
        self._g = int(self._g_scale.get_value())
        self._b = int(self._b_scale.get_value())
        # Sync spinbuttons
        self._r_spin.set_value(self._r)
        self._g_spin.set_value(self._g)
        self._b_spin.set_value(self._b)
        self._update_display()

    def _on_spin_rgb(self, spin):
        self._r = int(self._r_spin.get_value())
        self._g = int(self._g_spin.get_value())
        self._b = int(self._b_spin.get_value())
        self._r_scale.set_value(self._r)
        self._g_scale.set_value(self._g)
        self._b_scale.set_value(self._b)
        self._update_display()

    def _on_hex_entered(self, entry):
        hex_str = entry.get_text().strip()
        try:
            r, g, b = self._engine.hex_to_rgb(hex_str)
            self._set_rgb(r, g, b)
        except (ValueError, IndexError):
            pass

    def _set_rgb(self, r: int, g: int, b: int):
        self._r, self._g, self._b = r, g, b
        self._r_scale.set_value(r)
        self._g_scale.set_value(g)
        self._b_scale.set_value(b)
        self._r_spin.set_value(r)
        self._g_spin.set_value(g)
        self._b_spin.set_value(b)
        self._update_display()

    def _on_pick_screen(self, btn):
        result = self._engine.pick_from_screen()
        if result:
            self._set_rgb(*result)
            self._save_to_history()
        else:
            dlg = Gtk.MessageDialog(
                parent=self, flags=0, message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Screen picker unavailable",
            )
            dlg.format_secondary_text("Install 'xcolor' for screen picking: sudo apt install xcolor")
            dlg.run()
            dlg.destroy()

    def _on_copy_format(self, tree, path, col):
        it = self._format_store.get_iter(path)
        val = self._format_store.get_value(it, 1)
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(val, -1)

    def _on_copy_hex(self, btn):
        hex_val = self._engine.rgb_to_hex(self._r, self._g, self._b)
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(hex_val, -1)

    def _save_to_history(self):
        color = (self._r, self._g, self._b)
        if color in self._history:
            return
        self._history.insert(0, color)
        if len(self._history) > 20:
            self._history.pop()
        self._rebuild_history()

    def _rebuild_history(self):
        for child in self._history_box.get_children():
            self._history_box.remove(child)
        for r, g, b in self._history:
            swatch = Gtk.DrawingArea()
            swatch.set_size_request(28, 28)
            color = (r, g, b)
            swatch.connect("draw", lambda w, cr, c=color: self._draw_swatch(w, cr, c))
            swatch.set_tooltip_text(self._engine.rgb_to_hex(r, g, b))
            self._history_box.add(swatch)
        self._history_box.show_all()

    def _draw_swatch(self, widget, cr, color):
        r, g, b = color
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cr.arc(w / 2, h / 2, min(w, h) / 2 - 1, 0, 6.28)
        cr.fill()

    def _on_history_click(self, box, child):
        idx = box.get_children().index(child)
        if idx < len(self._history):
            r, g, b = self._history[idx]
            self._set_rgb(r, g, b)
