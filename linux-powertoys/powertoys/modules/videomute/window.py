"""VideoConferenceMute GTK3 window."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from .engine import VideoMuteEngine


class VideoMuteWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="Video Conference Mute")
        self.set_default_size(500, 420)
        self.set_border_width(0)
        if parent:
            self.set_transient_for(parent)

        self._engine = VideoMuteEngine()
        self._build_ui()
        self._refresh_devices()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Header
        header = Gtk.Box(spacing=12)
        header.set_border_width(16)
        icon = Gtk.Image.new_from_icon_name("audio-input-microphone", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        header.pack_start(icon, False, False, 0)
        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>Video Conference Mute</big></b>")
        hbox.pack_start(title, False, False, 0)
        sub = Gtk.Label(
            label="Quickly mute your microphone and block your camera during video calls.",
            xalign=0
        )
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("dim-label")
        hbox.pack_start(sub, False, False, 0)
        header.pack_start(hbox, True, True, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Microphone section
        mic_frame = Gtk.Frame(label=" Microphone ")
        mic_frame.set_border_width(8)
        mic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        mic_box.set_border_width(12)
        mic_frame.add(mic_box)

        # Device selector
        dev_row = Gtk.Box(spacing=8)
        dev_row.pack_start(Gtk.Label(label="Device:"), False, False, 0)
        self._mic_combo = Gtk.ComboBoxText()
        self._mic_combo.connect("changed", self._on_mic_selected)
        dev_row.pack_start(self._mic_combo, True, True, 0)
        btn_refresh_mic = Gtk.Button(label="Refresh")
        btn_refresh_mic.connect("clicked", lambda *a: self._refresh_devices())
        dev_row.pack_start(btn_refresh_mic, False, False, 0)
        mic_box.pack_start(dev_row, False, False, 0)

        # Mute toggle
        mute_row = Gtk.Box(spacing=12)
        self._mic_btn = Gtk.Button()
        self._mic_btn.set_size_request(160, 48)
        self._mic_btn.connect("clicked", self._on_toggle_mic)
        mute_row.pack_start(self._mic_btn, False, False, 0)

        self._mic_status_lbl = Gtk.Label(label="Ready")
        self._mic_status_lbl.get_style_context().add_class("dim-label")
        mute_row.pack_start(self._mic_status_lbl, False, False, 0)
        mic_box.pack_start(mute_row, False, False, 0)

        vbox.pack_start(mic_frame, False, False, 0)

        # Camera section
        cam_frame = Gtk.Frame(label=" Camera ")
        cam_frame.set_border_width(8)
        cam_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cam_box.set_border_width(12)
        cam_frame.add(cam_box)

        cam_row = Gtk.Box(spacing=8)
        cam_row.pack_start(Gtk.Label(label="Device:"), False, False, 0)
        self._cam_combo = Gtk.ComboBoxText()
        cam_row.pack_start(self._cam_combo, True, True, 0)
        cam_box.pack_start(cam_row, False, False, 0)

        cam_btn_row = Gtk.Box(spacing=12)
        self._cam_btn = Gtk.Button(label="Block Camera")
        self._cam_btn.set_size_request(160, 48)
        self._cam_btn.connect("clicked", self._on_toggle_cam)
        cam_btn_row.pack_start(self._cam_btn, False, False, 0)

        self._cam_status_lbl = Gtk.Label(label="Camera unblocked")
        self._cam_status_lbl.get_style_context().add_class("dim-label")
        cam_btn_row.pack_start(self._cam_status_lbl, False, False, 0)
        cam_box.pack_start(cam_btn_row, False, False, 0)

        cam_note = Gtk.Label(
            label="Note: Blocking camera requires root/sudo to change /dev/video* permissions.",
            xalign=0
        )
        cam_note.set_line_wrap(True)
        cam_note.get_style_context().add_class("dim-label")
        cam_box.pack_start(cam_note, False, False, 0)

        vbox.pack_start(cam_frame, False, False, 0)

        # Status bar
        self._status = Gtk.Statusbar()
        vbox.pack_start(self._status, False, False, 0)

        self._update_mic_btn()
        self.show_all()

    def _refresh_devices(self):
        # Microphones
        self._mic_combo.remove_all()
        mics = self._engine.get_microphones()
        if mics:
            for mic in mics:
                self._mic_combo.append_text(f"[{mic.index}] {mic.name}")
            self._mic_combo.set_active(0)
            self._engine.select_microphone(mics[0].index)
        else:
            self._mic_combo.append_text("(No microphone found)")
            self._mic_combo.set_active(0)

        # Cameras
        self._cam_combo.remove_all()
        cams = self._engine.get_cameras()
        if cams:
            for cam in cams:
                self._cam_combo.append_text(cam)
            self._cam_combo.set_active(0)
        else:
            self._cam_combo.append_text("(No camera found)")
            self._cam_combo.set_active(0)

        self._set_status(f"{len(mics)} mic(s), {len(cams)} camera(s) found")

    def _on_mic_selected(self, combo):
        idx = combo.get_active()
        mics = self._engine.get_microphones()
        if 0 <= idx < len(mics):
            self._engine.select_microphone(mics[idx].index)

    def _on_toggle_mic(self, btn):
        ok, msg = self._engine.toggle_mic()
        self._mic_status_lbl.set_text(msg)
        self._update_mic_btn()
        self._set_status(msg)

    def _update_mic_btn(self):
        if self._engine.mic_muted:
            self._mic_btn.set_label("Unmute Microphone")
            self._mic_btn.get_style_context().add_class("destructive-action")
            self._mic_btn.get_style_context().remove_class("suggested-action")
        else:
            self._mic_btn.set_label("Mute Microphone")
            self._mic_btn.get_style_context().remove_class("destructive-action")
            self._mic_btn.get_style_context().add_class("suggested-action")

    def _on_toggle_cam(self, btn):
        device = self._cam_combo.get_active_text() or ""
        if not device or device.startswith("("):
            self._cam_status_lbl.set_text("No camera device selected")
            return
        ok, msg = self._engine.toggle_camera(device)
        if ok:
            if self._engine.cam_blocked:
                self._cam_btn.set_label("Unblock Camera")
                self._cam_btn.get_style_context().add_class("destructive-action")
            else:
                self._cam_btn.set_label("Block Camera")
                self._cam_btn.get_style_context().remove_class("destructive-action")
        self._cam_status_lbl.set_text(msg)
        self._set_status(msg)

    def _set_status(self, msg: str):
        ctx = self._status.get_context_id("main")
        self._status.pop(ctx)
        self._status.push(ctx, msg)
