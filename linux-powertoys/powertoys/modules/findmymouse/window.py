"""FindMyMouse GTK3 window - spotlight overlay to locate the cursor."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import math
import threading

from .engine import FindMyMouseEngine


class _SpotlightOverlay(Gtk.Window):
    """Fullscreen dark overlay with a spotlight hole around the cursor."""

    def __init__(self, cx: int, cy: int, radius: int, opacity: float, on_done):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.fullscreen()

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self._cx = cx
        self._cy = cy
        self._radius = radius
        self._opacity = opacity
        self._on_done = on_done
        self._anim_radius = 0
        self._anim_step = 0
        self._total_steps = 20

        self.connect("draw", self._on_draw)
        self.connect("button-press-event", lambda *a: self._dismiss())
        self.connect("key-press-event", lambda *a: self._dismiss())
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.set_can_focus(True)

        self.show_all()
        self.grab_focus()
        GLib.timeout_add(20, self._animate)

    def _animate(self):
        self._anim_step += 1
        t = self._anim_step / self._total_steps
        # Ease out cubic
        t = 1 - (1 - t) ** 3
        self._anim_radius = int(self._radius * t)
        self.queue_draw()
        if self._anim_step >= self._total_steps:
            # Hold for a moment then pulse
            GLib.timeout_add(600, self._pulse_start)
            return False
        return True

    def _pulse_start(self):
        self._pulse_dir = -1
        self._pulse_count = 0
        GLib.timeout_add(30, self._pulse)

    def _pulse(self):
        self._pulse_count += 1
        self._anim_radius += self._pulse_dir * 4
        if self._anim_radius < self._radius - 30:
            self._pulse_dir = 1
        elif self._anim_radius > self._radius + 10:
            self._pulse_dir = -1
        self.queue_draw()
        if self._pulse_count > 30:
            GLib.timeout_add(300, self._dismiss)
            return False
        return True

    def _dismiss(self):
        self.destroy()
        if self._on_done:
            self._on_done()
        return False

    def _on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height

        # Dark overlay
        cr.set_source_rgba(0, 0, 0, self._opacity)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Cut out spotlight circle using destination-out
        cr.set_operator(1)  # CAIRO_OPERATOR_CLEAR = 1 via int
        cr.arc(self._cx, self._cy, max(1, self._anim_radius), 0, 2 * math.pi)
        cr.fill()

        # Bright ring around spotlight
        cr.set_operator(0)  # CAIRO_OPERATOR_OVER
        cr.set_source_rgba(1, 1, 0.3, 0.6)
        cr.set_line_width(3)
        cr.arc(self._cx, self._cy, max(1, self._anim_radius), 0, 2 * math.pi)
        cr.stroke()

        # Crosshair lines
        cr.set_source_rgba(1, 1, 0.3, 0.4)
        cr.set_line_width(1)
        cr.move_to(self._cx - self._anim_radius - 20, self._cy)
        cr.line_to(self._cx + self._anim_radius + 20, self._cy)
        cr.stroke()
        cr.move_to(self._cx, self._cy - self._anim_radius - 20)
        cr.line_to(self._cx, self._cy + self._anim_radius + 20)
        cr.stroke()


class FindMyMouseWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Find My Mouse")
        self.set_default_size(480, 360)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = FindMyMouseEngine()
        self._overlay: _SpotlightOverlay = None
        self._build_ui()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Header
        header = Gtk.Box(spacing=12)
        header.set_border_width(16)
        icon = Gtk.Image.new_from_icon_name("find-location-symbolic", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        header.pack_start(icon, False, False, 0)

        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>Find My Mouse</big></b>")
        hbox.pack_start(title, False, False, 0)
        sub = Gtk.Label(
            label="Highlight the cursor with a spotlight effect so you never lose it.",
            xalign=0
        )
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("dim-label")
        hbox.pack_start(sub, False, False, 0)
        header.pack_start(hbox, True, True, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Settings grid
        grid = Gtk.Grid(row_spacing=12, column_spacing=16)
        grid.set_border_width(16)

        row = 0

        lbl = Gtk.Label(label="Spotlight radius (px):", xalign=0)
        grid.attach(lbl, 0, row, 1, 1)
        self._radius_spin = Gtk.SpinButton.new_with_range(40, 300, 10)
        self._radius_spin.set_value(self._engine.spotlight_radius)
        grid.attach(self._radius_spin, 1, row, 1, 1)
        row += 1

        lbl = Gtk.Label(label="Overlay opacity:", xalign=0)
        grid.attach(lbl, 0, row, 1, 1)
        self._opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 0.95, 0.05)
        self._opacity_scale.set_value(self._engine.overlay_opacity)
        self._opacity_scale.set_hexpand(True)
        self._opacity_scale.set_size_request(200, -1)
        grid.attach(self._opacity_scale, 1, row, 1, 1)
        row += 1

        lbl = Gtk.Label(label="Shake mouse to activate:", xalign=0)
        grid.attach(lbl, 0, row, 1, 1)
        self._shake_check = Gtk.CheckButton()
        self._shake_check.set_active(self._engine.shake_to_activate)
        grid.attach(self._shake_check, 1, row, 1, 1)
        row += 1

        vbox.pack_start(grid, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Activate button
        btn_box = Gtk.Box(spacing=8)
        btn_box.set_border_width(16)

        btn_find = Gtk.Button(label="Find My Mouse Now")
        btn_find.get_style_context().add_class("suggested-action")
        btn_find.set_size_request(200, 40)
        btn_find.connect("clicked", self._on_find)
        btn_box.pack_start(btn_find, False, False, 0)

        self._pos_label = Gtk.Label(label="")
        self._pos_label.get_style_context().add_class("dim-label")
        btn_box.pack_start(self._pos_label, False, False, 8)

        vbox.pack_start(btn_box, False, False, 0)

        # Info
        info = Gtk.InfoBar()
        info.set_message_type(Gtk.MessageType.INFO)
        info.get_content_area().add(Gtk.Label(
            label="Click anywhere on the overlay or press any key to dismiss the spotlight."
        ))
        vbox.pack_start(info, False, False, 0)

        self.show_all()

    def _on_find(self, btn):
        self._engine.spotlight_radius = int(self._radius_spin.get_value())
        self._engine.overlay_opacity = self._opacity_scale.get_value()
        self._engine.shake_to_activate = self._shake_check.get_active()

        pos = self._engine.get_cursor_position()
        if pos is None:
            self._pos_label.set_text("Could not detect cursor (xdotool required)")
            return

        cx, cy = pos
        self._pos_label.set_text(f"Cursor at ({cx}, {cy})")

        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass

        self._overlay = _SpotlightOverlay(
            cx, cy,
            self._engine.spotlight_radius,
            self._engine.overlay_opacity,
            on_done=lambda: setattr(self, "_overlay", None),
        )
