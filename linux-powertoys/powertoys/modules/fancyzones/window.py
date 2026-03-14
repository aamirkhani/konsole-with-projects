"""FancyZones GTK3 window - visual window layout manager."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, cairo

import math
from .engine import FancyZonesEngine, Layout, Zone, BUILTIN_LAYOUTS


class _ZoneLayoutPreview(Gtk.DrawingArea):
    """Canvas that shows a visual preview of a layout's zones."""

    def __init__(self, layout: Layout = None):
        super().__init__()
        self.set_size_request(280, 160)
        self._layout = layout
        self.connect("draw", self._on_draw)

    def set_layout(self, layout: Layout):
        self._layout = layout
        self.queue_draw()

    def _on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        pad = 12

        # Background
        cr.set_source_rgb(0.13, 0.13, 0.16)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        if not self._layout:
            return

        for zone in self._layout.zones:
            zx = pad + zone.x * (w - 2 * pad)
            zy = pad + zone.y * (h - 2 * pad)
            zw = zone.width * (w - 2 * pad) - 4
            zh = zone.height * (h - 2 * pad) - 4

            # Zone fill
            cr.set_source_rgba(0.09, 0.57, 1.0, 0.35)
            cr.rectangle(zx, zy, zw, zh)
            cr.fill()

            # Zone border
            cr.set_source_rgba(0.09, 0.57, 1.0, 0.8)
            cr.set_line_width(1.5)
            cr.rectangle(zx, zy, zw, zh)
            cr.stroke()

            # Zone name
            if zone.name:
                cr.set_source_rgb(1, 1, 1)
                cr.set_font_size(10)
                cr.move_to(zx + 6, zy + 16)
                cr.show_text(zone.name)


class _CustomLayoutEditor(Gtk.Dialog):
    """Dialog to create a custom zone layout by dragging."""

    def __init__(self, parent):
        super().__init__(title="Custom Layout Editor", transient_for=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(600, 400)

        self._zones: list[Zone] = []
        self._selected_zone: int = -1
        self._drag_start = None
        self._draw_start = None
        self._draw_cur = None

        content = self.get_content_area()
        content.set_border_width(8)

        # Info bar
        info = Gtk.Label(label="Click and drag on the canvas to create zones. Right-click to delete.")
        info.set_line_wrap(True)
        content.pack_start(info, False, False, 4)

        # Canvas
        self._canvas = Gtk.DrawingArea()
        self._canvas.set_size_request(560, 300)
        self._canvas.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self._canvas.connect("draw", self._on_draw)
        self._canvas.connect("button-press-event", self._on_press)
        self._canvas.connect("button-release-event", self._on_release)
        self._canvas.connect("motion-notify-event", self._on_motion)
        content.pack_start(self._canvas, True, True, 0)

        # Name row
        name_box = Gtk.Box(spacing=6)
        name_box.pack_start(Gtk.Label(label="Layout name:"), False, False, 0)
        self._name_entry = Gtk.Entry()
        self._name_entry.set_text("Custom Layout")
        name_box.pack_start(self._name_entry, True, True, 0)
        content.pack_start(name_box, False, False, 4)

        content.pack_start(Gtk.Button(label="Clear All Zones"), False, False, 0)
        content.get_children()[-1].connect("clicked", lambda *a: self._clear())

        self.show_all()

    def _get_canvas_size(self):
        a = self._canvas.get_allocation()
        return a.width, a.height

    def _on_draw(self, widget, cr):
        w, h = self._get_canvas_size()
        cr.set_source_rgb(0.1, 0.1, 0.12)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Grid
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.3)
        cr.set_line_width(0.5)
        for i in range(1, 4):
            cr.move_to(w * i / 4, 0); cr.line_to(w * i / 4, h)
            cr.move_to(0, h * i / 4); cr.line_to(w, h * i / 4)
        cr.stroke()

        for i, zone in enumerate(self._zones):
            zx = zone.x * w; zy = zone.y * h
            zw = zone.width * w; zh = zone.height * h
            selected = (i == self._selected_zone)
            cr.set_source_rgba(0.09, 0.57, 1.0, 0.5 if selected else 0.25)
            cr.rectangle(zx + 2, zy + 2, zw - 4, zh - 4)
            cr.fill()
            cr.set_source_rgba(0.09, 0.57, 1.0, 1.0 if selected else 0.6)
            cr.set_line_width(2 if selected else 1)
            cr.rectangle(zx + 2, zy + 2, zw - 4, zh - 4)
            cr.stroke()
            cr.set_source_rgb(1, 1, 1)
            cr.set_font_size(12)
            cr.move_to(zx + 8, zy + 20)
            cr.show_text(f"Zone {i+1}")

        # Draw in-progress zone
        if self._draw_start and self._draw_cur:
            sx, sy = self._draw_start
            cx, cy = self._draw_cur
            cr.set_source_rgba(1, 0.8, 0, 0.4)
            cr.rectangle(min(sx, cx), min(sy, cy), abs(cx - sx), abs(cy - sy))
            cr.fill()
            cr.set_source_rgba(1, 0.8, 0, 0.9)
            cr.set_line_width(2)
            cr.rectangle(min(sx, cx), min(sy, cy), abs(cx - sx), abs(cy - sy))
            cr.stroke()

    def _on_press(self, widget, event):
        w, h = self._get_canvas_size()
        if event.button == 1:
            self._draw_start = (event.x, event.y)
            self._draw_cur = (event.x, event.y)
        elif event.button == 3:
            # Right-click: delete zone under cursor
            px, py = event.x / w, event.y / h
            for i, zone in enumerate(self._zones):
                if zone.x <= px <= zone.x + zone.width and zone.y <= py <= zone.y + zone.height:
                    self._zones.pop(i)
                    self._canvas.queue_draw()
                    break

    def _on_motion(self, widget, event):
        if self._draw_start:
            self._draw_cur = (event.x, event.y)
            self._canvas.queue_draw()

    def _on_release(self, widget, event):
        if self._draw_start and event.button == 1:
            w, h = self._get_canvas_size()
            sx, sy = self._draw_start
            ex, ey = event.x, event.y
            zx = min(sx, ex) / w; zy = min(sy, ey) / h
            zw = abs(ex - sx) / w; zh = abs(ey - sy) / h
            if zw > 0.02 and zh > 0.02:
                self._zones.append(Zone(x=zx, y=zy, width=zw, height=zh, name=f"Zone {len(self._zones)+1}"))
            self._draw_start = None
            self._draw_cur = None
            self._canvas.queue_draw()

    def _clear(self):
        self._zones.clear()
        self._canvas.queue_draw()

    def get_layout(self) -> Layout:
        return Layout(name=self._name_entry.get_text() or "Custom", zones=list(self._zones))


class FancyZonesWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="FancyZones")
        self.set_default_size(800, 600)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = FancyZonesEngine()
        self._selected_layout: Layout = BUILTIN_LAYOUTS[0]

        self._build_ui()
        self._select_layout(self._selected_layout)

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        vbox.pack_start(self._build_toolbar(), False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        hbox = Gtk.Box(spacing=0)
        vbox.pack_start(hbox, True, True, 0)

        hbox.pack_start(self._build_layout_list(), False, False, 0)
        hbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        hbox.pack_start(self._build_preview_panel(), True, True, 0)

        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self.show_all()

    def _build_toolbar(self):
        bar = Gtk.Box(spacing=4)
        bar.set_border_width(6)

        btn_activate = Gtk.Button(label="Activate Layout")
        btn_activate.get_style_context().add_class("suggested-action")
        btn_activate.connect("clicked", self._on_activate)
        bar.pack_start(btn_activate, False, False, 0)

        btn_tile = Gtk.Button(label="Tile All Windows")
        btn_tile.connect("clicked", self._on_tile_all)
        bar.pack_start(btn_tile, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        btn_custom = Gtk.Button(label="+ Custom Layout")
        btn_custom.connect("clicked", self._on_custom)
        bar.pack_start(btn_custom, False, False, 0)

        # Gap control
        bar.pack_end(Gtk.Label(label="Gap (px):"), False, False, 4)
        self._gap_spin = Gtk.SpinButton.new_with_range(0, 40, 1)
        self._gap_spin.set_value(self._engine.gap)
        self._gap_spin.connect("value-changed", lambda s: setattr(self._engine, "gap", int(s.get_value())))
        bar.pack_end(self._gap_spin, False, False, 0)

        return bar

    def _build_layout_list(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_size_request(220, -1)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Layouts</b>")
        lbl.set_border_width(8)
        box.pack_start(lbl, False, False, 0)

        self._layout_store = Gtk.ListStore(str)
        self._layout_tree = Gtk.TreeView(model=self._layout_store)
        self._layout_tree.set_headers_visible(False)

        rend = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("", rend, text=0)
        self._layout_tree.append_column(col)
        self._layout_tree.connect("cursor-changed", self._on_layout_selected)

        for layout in self._engine.layouts:
            self._layout_store.append([layout.name])

        scroll = Gtk.ScrolledWindow()
        scroll.add(self._layout_tree)
        box.pack_start(scroll, True, True, 0)

        return box

    def _build_preview_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        # Layout name
        self._layout_title = Gtk.Label(xalign=0)
        self._layout_title.set_markup("<big><b>—</b></big>")
        box.pack_start(self._layout_title, False, False, 0)

        # Preview
        self._preview = _ZoneLayoutPreview()
        box.pack_start(self._preview, False, False, 0)

        # Zone list
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Zones</b>")
        box.pack_start(lbl, False, False, 0)

        self._zone_store = Gtk.ListStore(str, str, str, str)
        zone_tree = Gtk.TreeView(model=self._zone_store)
        zone_tree.set_headers_visible(True)

        for i, (title, col_id) in enumerate([
            ("Name", 0), ("X", 1), ("Y", 2), ("Size", 3)
        ]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=col_id)
            col.set_expand(i == 0)
            zone_tree.append_column(col)

        zone_scroll = Gtk.ScrolledWindow()
        zone_scroll.set_min_content_height(100)
        zone_scroll.add(zone_tree)
        box.pack_start(zone_scroll, True, True, 0)

        # Snap buttons (for manual snapping)
        snap_lbl = Gtk.Label(xalign=0)
        snap_lbl.set_markup("<b>Snap Active Window to Zone</b>")
        box.pack_start(snap_lbl, False, False, 0)

        self._snap_box = Gtk.FlowBox()
        self._snap_box.set_max_children_per_line(6)
        box.pack_start(self._snap_box, False, False, 0)

        return box

    # ── Logic ──────────────────────────────────────────────────────────────

    def _select_layout(self, layout: Layout):
        self._selected_layout = layout
        self._layout_title.set_markup(f"<big><b>{layout.name}</b></big>")
        self._preview.set_layout(layout)

        self._zone_store.clear()
        for z in layout.zones:
            self._zone_store.append([
                z.name,
                f"{z.x*100:.0f}%",
                f"{z.y*100:.0f}%",
                f"{z.width*100:.0f}% × {z.height*100:.0f}%",
            ])

        # Rebuild snap buttons
        for child in self._snap_box.get_children():
            self._snap_box.remove(child)
        for i, zone in enumerate(layout.zones):
            btn = Gtk.Button(label=zone.name or f"Zone {i+1}")
            btn.connect("clicked", lambda b, idx=i: self._engine.snap_active_window(idx))
            self._snap_box.add(btn)
        self._snap_box.show_all()

    def _on_layout_selected(self, tree):
        model, it = tree.get_selection().get_selected()
        if it is None:
            return
        idx = int(str(model.get_path(it)))
        if 0 <= idx < len(self._engine.layouts):
            self._select_layout(self._engine.layouts[idx])

    def _on_activate(self, btn):
        self._engine.activate_layout(self._selected_layout)
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, f"Layout '{self._selected_layout.name}' activated")

    def _on_tile_all(self, btn):
        self._engine.activate_layout(self._selected_layout)
        self._engine.tile_all_windows()

    def _on_custom(self, btn):
        dlg = _CustomLayoutEditor(self)
        if dlg.run() == Gtk.ResponseType.OK:
            layout = dlg.get_layout()
            if layout.zones:
                self._engine.add_custom_layout(layout)
                self._layout_store.append([layout.name])
        dlg.destroy()
