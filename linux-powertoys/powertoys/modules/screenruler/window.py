"""ScreenRuler GTK3 window - on-screen pixel ruler."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, cairo

import math
from .ruler import ScreenRulerEngine


class ScreenRulerWindow(Gtk.Window):
    """A resizable on-screen ruler that measures pixels."""

    def __init__(self, parent=None):
        super().__init__(title="Screen Ruler")
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_default_size(600, 60)
        self.set_border_width(0)
        self.set_resizable(True)
        if parent:
            self.set_transient_for(parent)

        self._engine = ScreenRulerEngine()
        self._unit = "Pixels"
        self._orientation = "horizontal"  # or "vertical"
        self._opacity = 0.85
        self._dragging = False
        self._drag_x = self._drag_y = 0
        self._ruler_color = (0.95, 0.88, 0.25)  # Yellow ruler

        self.set_opacity(self._opacity)
        self._build_ui()
        self.show_all()

    def _build_ui(self):
        overlay = Gtk.Overlay()
        self.add(overlay)

        # Drawing area (the ruler itself)
        self._ruler_area = Gtk.DrawingArea()
        self._ruler_area.connect("draw", self._on_draw_ruler)
        self._ruler_area.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.SCROLL_MASK
        )
        self._ruler_area.connect("button-press-event", self._on_press)
        self._ruler_area.connect("button-release-event", self._on_release)
        self._ruler_area.connect("motion-notify-event", self._on_motion)
        self._ruler_area.connect("scroll-event", self._on_scroll)
        overlay.add(self._ruler_area)

        # Control strip (visible on hover)
        ctrl_bar = Gtk.Box(spacing=4)
        ctrl_bar.set_halign(Gtk.Align.END)
        ctrl_bar.set_valign(Gtk.Align.START)
        ctrl_bar.set_margin_top(4)
        ctrl_bar.set_margin_end(4)

        # Unit selector
        self._unit_combo = Gtk.ComboBoxText()
        for unit in ScreenRulerEngine.UNITS:
            self._unit_combo.append_text(unit)
        self._unit_combo.set_active(0)
        self._unit_combo.connect("changed", self._on_unit_changed)
        ctrl_bar.pack_start(self._unit_combo, False, False, 0)

        # Rotate
        btn_rotate = Gtk.Button(label="⟳")
        btn_rotate.set_tooltip_text("Rotate ruler")
        btn_rotate.connect("clicked", self._on_rotate)
        ctrl_bar.pack_start(btn_rotate, False, False, 0)

        # Close
        btn_close = Gtk.Button(label="✕")
        btn_close.connect("clicked", lambda *a: self.destroy())
        ctrl_bar.pack_start(btn_close, False, False, 0)

        overlay.add_overlay(ctrl_bar)

        # Cursor position tracking
        self._cursor_x = 0
        self._cursor_y = 0
        self._mark_x = -1  # measurement mark

        self.connect("key-press-event", self._on_key)

    def _on_draw_ruler(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        length = w if self._orientation == "horizontal" else h
        thickness = h if self._orientation == "horizontal" else w

        # Ruler background
        r, g, b = self._ruler_color
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Border
        cr.set_source_rgb(0.2, 0.2, 0.2)
        cr.set_line_width(1)
        cr.rectangle(0, 0, w, h)
        cr.stroke()

        # Tick marks
        cr.set_source_rgb(0, 0, 0)
        cr.set_font_size(9)

        for px in range(0, int(length), 1):
            if px % 100 == 0:
                tick_h = thickness * 0.5
                cr.set_line_width(1.2)
            elif px % 50 == 0:
                tick_h = thickness * 0.35
                cr.set_line_width(1.0)
            elif px % 10 == 0:
                tick_h = thickness * 0.25
                cr.set_line_width(0.8)
            elif px % 5 == 0:
                tick_h = thickness * 0.15
                cr.set_line_width(0.6)
            else:
                continue

            if self._orientation == "horizontal":
                cr.move_to(px, 0)
                cr.line_to(px, tick_h)
                cr.move_to(px, h)
                cr.line_to(px, h - tick_h)
            else:
                cr.move_to(0, px)
                cr.line_to(tick_h, px)
                cr.move_to(w, px)
                cr.line_to(w - tick_h, px)
            cr.stroke()

            # Labels at 100-pixel marks
            if px % 100 == 0 and px > 0:
                label = self._engine.convert(px, self._unit)
                if self._orientation == "horizontal":
                    cr.move_to(px + 2, thickness * 0.5 - 2)
                else:
                    cr.move_to(2, px - 2)
                cr.show_text(label)

        # Cursor indicator
        cr.set_source_rgba(1, 0, 0, 0.8)
        cr.set_line_width(1.5)
        if self._orientation == "horizontal":
            cr.move_to(self._cursor_x, 0)
            cr.line_to(self._cursor_x, h)
        else:
            cr.move_to(0, self._cursor_y)
            cr.line_to(w, self._cursor_y)
        cr.stroke()

        # Measurement mark
        if self._mark_x >= 0:
            cr.set_source_rgba(0, 0, 1, 0.7)
            cr.set_line_width(1.5)
            if self._orientation == "horizontal":
                cr.move_to(self._mark_x, 0)
                cr.line_to(self._mark_x, h)
                # Distance label
                dist = abs(self._cursor_x - self._mark_x)
                cr.set_source_rgba(0, 0, 1, 1)
                cr.set_font_size(11)
                cr.move_to(min(self._cursor_x, self._mark_x) + 4, h / 2 + 5)
                cr.show_text(self._engine.convert(dist, self._unit))
            else:
                cr.move_to(0, self._mark_x)
                cr.line_to(w, self._mark_x)
            cr.stroke()

        # Size label
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.set_font_size(10)
        size_label = self._engine.convert(length, self._unit)
        if self._orientation == "horizontal":
            cr.move_to(4, h - 4)
        else:
            cr.move_to(4, h - 4)
        cr.show_text(f"Size: {size_label}  |  DPI: {self._engine.dpi}")

    def _on_press(self, widget, event):
        if event.button == 1:
            self._dragging = True
            wx, wy = self.get_position()
            self._drag_x = int(event.x_root) - wx
            self._drag_y = int(event.y_root) - wy
        elif event.button == 3:
            # Right-click: set/clear measurement mark
            if self._orientation == "horizontal":
                self._mark_x = int(event.x) if self._mark_x < 0 else -1
            else:
                self._mark_x = int(event.y) if self._mark_x < 0 else -1
            self._ruler_area.queue_draw()

    def _on_release(self, widget, event):
        self._dragging = False

    def _on_motion(self, widget, event):
        if self._dragging:
            new_x = int(event.x_root) - self._drag_x
            new_y = int(event.y_root) - self._drag_y
            self.move(new_x, new_y)
        else:
            self._cursor_x = int(event.x)
            self._cursor_y = int(event.y)
            self._ruler_area.queue_draw()

    def _on_scroll(self, widget, event):
        """Resize the ruler with scroll wheel."""
        w, h = self.get_size()
        delta = 10 if event.direction == Gdk.ScrollDirection.DOWN else -10
        if self._orientation == "horizontal":
            self.resize(max(100, w + delta), h)
        else:
            self.resize(w, max(100, h + delta))

    def _on_rotate(self, btn):
        w, h = self.get_size()
        self._orientation = "vertical" if self._orientation == "horizontal" else "horizontal"
        self.resize(h, w)
        self._mark_x = -1

    def _on_unit_changed(self, combo):
        self._unit = combo.get_active_text()
        self._ruler_area.queue_draw()

    def _on_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
        elif event.keyval == Gdk.KEY_r:
            self._on_rotate(None)


class ScreenRulerSettingsWindow(Gtk.Window):
    """Settings/launcher for the Screen Ruler."""

    def __init__(self, parent=None):
        super().__init__(title="Screen Ruler")
        self.set_default_size(380, 200)
        self.set_resizable(False)
        if parent:
            self.set_transient_for(parent)

        self._ruler = None
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(16)
        self.add(vbox)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Screen Ruler</b>\nMeasure distances on screen in pixels, cm, inches, or points.")
        lbl.set_line_wrap(True)
        vbox.pack_start(lbl, False, False, 0)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        btn_launch = Gtk.Button(label="Launch Ruler")
        btn_launch.get_style_context().add_class("suggested-action")
        btn_launch.set_size_request(-1, 48)
        btn_launch.connect("clicked", self._on_launch)
        vbox.pack_start(btn_launch, False, False, 0)

        tips = Gtk.Label(xalign=0)
        tips.set_markup(
            "<small>"
            "• <b>Left-click drag</b>: move the ruler\n"
            "• <b>Right-click</b>: set/clear measurement mark\n"
            "• <b>Scroll wheel</b>: resize the ruler\n"
            "• <b>R key</b>: rotate horizontal/vertical\n"
            "• <b>Esc</b>: close ruler"
            "</small>"
        )
        tips.set_line_wrap(True)
        vbox.pack_start(tips, False, False, 0)

        self.show_all()

    def _on_launch(self, btn):
        if self._ruler and self._ruler.get_visible():
            self._ruler.destroy()
        self._ruler = ScreenRulerWindow(parent=self)
        self._ruler.show_all()
