"""Awake GTK3 window - full UI for preventing system sleep."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .awake import AwakeEngine


class AwakeWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Awake")
        self.set_default_size(420, 320)
        self.set_resizable(False)
        if parent:
            self.set_transient_for(parent)

        self._engine = AwakeEngine()
        self._timer_id = None

        self._build_ui()
        self.connect("destroy", self._on_destroy)

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(16)
        self.add(vbox)

        # Status icon area
        self._icon = Gtk.Image.new_from_icon_name("weather-clear-night", Gtk.IconSize.DIALOG)
        vbox.pack_start(self._icon, False, False, 0)

        self._status_lbl = Gtk.Label()
        self._status_lbl.set_markup("<big><b>System can sleep normally</b></big>")
        vbox.pack_start(self._status_lbl, False, False, 0)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Mode selection
        mode_lbl = Gtk.Label(xalign=0)
        mode_lbl.set_markup("<b>Keep awake mode:</b>")
        vbox.pack_start(mode_lbl, False, False, 0)

        self._mode_indefinite = Gtk.RadioButton(label="Keep awake indefinitely")
        vbox.pack_start(self._mode_indefinite, False, False, 0)

        self._mode_timed = Gtk.RadioButton.new_with_label_from_widget(self._mode_indefinite, "Keep awake for a duration:")
        vbox.pack_start(self._mode_timed, False, False, 0)

        duration_box = Gtk.Box(spacing=6)
        duration_box.set_margin_start(24)
        vbox.pack_start(duration_box, False, False, 0)
        duration_box.pack_start(Gtk.Label(label="Hours:"), False, False, 0)
        self._hours_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self._hours_spin.set_value(1)
        duration_box.pack_start(self._hours_spin, False, False, 0)
        duration_box.pack_start(Gtk.Label(label="Minutes:"), False, False, 0)
        self._minutes_spin = Gtk.SpinButton.new_with_range(0, 59, 1)
        self._minutes_spin.set_value(0)
        duration_box.pack_start(self._minutes_spin, False, False, 0)

        self._mode_timed.connect("toggled", lambda b: duration_box.set_sensitive(b.get_active()))
        duration_box.set_sensitive(False)

        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Options
        self._no_screensaver = Gtk.CheckButton(label="Also disable screensaver")
        self._no_screensaver.set_active(True)
        vbox.pack_start(self._no_screensaver, False, False, 0)

        # Toggle button
        self._toggle_btn = Gtk.Button(label="Keep Awake")
        self._toggle_btn.set_size_request(-1, 48)
        self._toggle_btn.get_style_context().add_class("suggested-action")
        self._toggle_btn.connect("clicked", self._on_toggle)
        vbox.pack_start(self._toggle_btn, False, False, 8)

        # Elapsed timer
        self._elapsed_lbl = Gtk.Label(label="")
        self._elapsed_lbl.get_style_context().add_class("dim-label")
        vbox.pack_start(self._elapsed_lbl, False, False, 0)

        self.show_all()

    def _on_toggle(self, btn):
        if self._engine.active:
            self._engine.stop()
            if self._no_screensaver.get_active():
                self._engine.disable_screensaver(False)
            self._update_ui_inactive()
        else:
            mode = "timed" if self._mode_timed.get_active() else "indefinite"
            duration = int(self._hours_spin.get_value()) * 3600 + int(self._minutes_spin.get_value()) * 60
            if mode == "timed" and duration == 0:
                duration = 3600
            self._engine.start(mode=mode, duration=duration)
            if self._no_screensaver.get_active():
                self._engine.disable_screensaver(True)
            self._update_ui_active(duration if mode == "timed" else None)

    def _update_ui_active(self, duration_sec=None):
        self._icon.set_from_icon_name("weather-clear", Gtk.IconSize.DIALOG)
        self._status_lbl.set_markup("<big><b>Keeping system awake</b></big>")
        self._toggle_btn.set_label("Stop Keeping Awake")
        self._toggle_btn.get_style_context().remove_class("suggested-action")
        self._toggle_btn.get_style_context().add_class("destructive-action")

        import time
        self._start_time = time.time()
        self._duration = duration_sec

        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(1000, self._update_elapsed)

    def _update_ui_inactive(self):
        self._icon.set_from_icon_name("weather-clear-night", Gtk.IconSize.DIALOG)
        self._status_lbl.set_markup("<big><b>System can sleep normally</b></big>")
        self._toggle_btn.set_label("Keep Awake")
        self._toggle_btn.get_style_context().remove_class("destructive-action")
        self._toggle_btn.get_style_context().add_class("suggested-action")
        self._elapsed_lbl.set_text("")
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _update_elapsed(self):
        import time
        elapsed = int(time.time() - self._start_time)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        elapsed_str = f"Active for: {h:02d}:{m:02d}:{s:02d}"
        if self._duration:
            remaining = max(0, self._duration - elapsed)
            rh, rrem = divmod(remaining, 3600)
            rm, rs = divmod(rrem, 60)
            elapsed_str += f"  •  Remaining: {rh:02d}:{rm:02d}:{rs:02d}"
            if remaining == 0:
                self._engine.stop()
                self._update_ui_inactive()
                return False
        self._elapsed_lbl.set_text(elapsed_str)
        return True

    def _on_destroy(self, win):
        self._engine.stop()
