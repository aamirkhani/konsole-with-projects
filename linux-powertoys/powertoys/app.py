"""
Linux PowerToys - Main Settings Application
Central hub for all PowerToys modules with sidebar navigation.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gio

import os
import sys
from pathlib import Path

from . import __version__
from . import config

# Lazy-import module windows to avoid loading GTK until needed
_MODULE_REGISTRY = [
    {
        "id": "powerrename",
        "name": "PowerRename",
        "description": "Batch rename files and directories with regex and case transforms",
        "icon": "edit-find-replace",
        "category": "Files",
        "module": "powertoys.modules.powerrename",
        "window_class": "PowerRenameWindow",
    },
    {
        "id": "imageresizer",
        "name": "Image Resizer",
        "description": "Resize one or many images at once with preset sizes or custom dimensions",
        "icon": "image-x-generic",
        "category": "Files",
        "module": "powertoys.modules.imageresizer",
        "window_class": "ImageResizerWindow",
    },
    {
        "id": "filelocksmith",
        "name": "File Locksmith",
        "description": "Find which processes have files or directories open",
        "icon": "system-lock-screen",
        "category": "System",
        "module": "powertoys.modules.filelocksmith",
        "window_class": "FileLocksmithWindow",
    },
    {
        "id": "hostseditor",
        "name": "Hosts File Editor",
        "description": "Visual editor for /etc/hosts with add, edit, disable, and backup support",
        "icon": "network-server",
        "category": "Network",
        "module": "powertoys.modules.hostseditor",
        "window_class": "HostsEditorWindow",
    },
    {
        "id": "colorpicker",
        "name": "Color Picker",
        "description": "Pick colors from the screen and convert between HEX, RGB, HSL, and more",
        "icon": "color-picker",
        "category": "Utilities",
        "module": "powertoys.modules.colorpicker",
        "window_class": "ColorPickerWindow",
    },
    {
        "id": "run",
        "name": "PowerToys Run",
        "description": "Quick application launcher with calculator, file search and system commands",
        "icon": "system-search",
        "category": "Utilities",
        "module": "powertoys.modules.run",
        "window_class": "RunWindow",
    },
    {
        "id": "fancyzones",
        "name": "FancyZones",
        "description": "Window layout manager for tiling windows into configurable zones",
        "icon": "view-grid-symbolic",
        "category": "Windows",
        "module": "powertoys.modules.fancyzones",
        "window_class": "FancyZonesWindow",
    },
    {
        "id": "awake",
        "name": "Awake",
        "description": "Keep your system awake and prevent sleep or screen timeout",
        "icon": "weather-clear",
        "category": "System",
        "module": "powertoys.modules.awake",
        "window_class": "AwakeWindow",
    },
    {
        "id": "keyboard",
        "name": "Keyboard Manager",
        "description": "Remap keys and keyboard shortcuts system-wide",
        "icon": "input-keyboard",
        "category": "Input",
        "module": "powertoys.modules.keyboard",
        "window_class": "KeyboardManagerWindow",
    },
    {
        "id": "screenruler",
        "name": "Screen Ruler",
        "description": "On-screen ruler to measure pixel distances in multiple units",
        "icon": "document-page-setup",
        "category": "Utilities",
        "module": "powertoys.modules.screenruler",
        "window_class": "ScreenRulerSettingsWindow",
    },
    {
        "id": "textextractor",
        "name": "Text Extractor",
        "description": "Extract text from images and screen regions using OCR (tesseract)",
        "icon": "text-x-generic",
        "category": "Utilities",
        "module": "powertoys.modules.textextractor",
        "window_class": "TextExtractorWindow",
    },
    {
        "id": "clipboard",
        "name": "Clipboard History",
        "description": "Keep track of everything you copy with searchable clipboard history",
        "icon": "edit-paste",
        "category": "Utilities",
        "module": "powertoys.modules.clipboard",
        "window_class": "ClipboardWindow",
    },
    {
        "id": "alwaysontop",
        "name": "Always on Top",
        "description": "Pin any window to keep it always visible above all other windows",
        "icon": "go-up",
        "category": "Windows",
        "module": "powertoys.modules.alwaysontop",
        "window_class": "AlwaysOnTopWindow",
    },
    {
        "id": "envvars",
        "name": "Environment Variables",
        "description": "Visual editor for session, profile, and system environment variables",
        "icon": "preferences-system",
        "category": "System",
        "module": "powertoys.modules.envvars",
        "window_class": "EnvVarsWindow",
    },
    {
        "id": "findmymouse",
        "name": "Find My Mouse",
        "description": "Locate the cursor instantly with a spotlight/sonar effect",
        "icon": "input-mouse",
        "category": "Utilities",
        "module": "powertoys.modules.findmymouse",
        "window_class": "FindMyMouseWindow",
    },
    {
        "id": "pasteplain",
        "name": "Paste As Plain Text",
        "description": "Strip HTML, Markdown, and other formatting from clipboard content",
        "icon": "edit-clear",
        "category": "Utilities",
        "module": "powertoys.modules.pasteplain",
        "window_class": "PastePlainWindow",
    },
    {
        "id": "peek",
        "name": "Peek",
        "description": "Quick file previewer for text, images, archives, and more",
        "icon": "document-open",
        "category": "Files",
        "module": "powertoys.modules.peek",
        "window_class": "PeekSettingsWindow",
    },
    {
        "id": "shortcutguide",
        "name": "Shortcut Guide",
        "description": "Searchable reference of Linux, desktop, and application keyboard shortcuts",
        "icon": "input-keyboard",
        "category": "Input",
        "module": "powertoys.modules.shortcutguide",
        "window_class": "ShortcutGuideWindow",
    },
    {
        "id": "videomute",
        "name": "Video Conference Mute",
        "description": "Instantly mute your microphone and block camera during video calls",
        "icon": "audio-input-microphone",
        "category": "Utilities",
        "module": "powertoys.modules.videomute",
        "window_class": "VideoMuteWindow",
    },
    {
        "id": "workspaces",
        "name": "Workspaces",
        "description": "Save and restore complete window layout configurations",
        "icon": "view-grid-symbolic",
        "category": "Windows",
        "module": "powertoys.modules.workspaces",
        "window_class": "WorkspacesWindow",
    },
]

CATEGORIES = ["All", "Files", "Utilities", "System", "Windows", "Network", "Input"]


class ModuleCard(Gtk.Box):
    """A card widget for displaying a PowerToys module in the grid."""

    def __init__(self, module_info: dict, on_launch, on_toggle):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(240, 140)
        self.get_style_context().add_class("module-card")

        mod_id = module_info["id"]
        enabled = config.get(f"modules.{mod_id}.enabled", True)

        # Top: icon + name + toggle
        top = Gtk.Box(spacing=8)
        top.set_border_width(12)

        icon = Gtk.Image.new_from_icon_name(module_info["icon"], Gtk.IconSize.DND)
        icon.set_pixel_size(32)
        top.pack_start(icon, False, False, 0)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{module_info['name']}</b>")
        title_box.pack_start(title, False, False, 0)

        category_lbl = Gtk.Label(label=module_info["category"], xalign=0)
        category_lbl.get_style_context().add_class("dim-label")
        title_box.pack_start(category_lbl, False, False, 0)

        top.pack_start(title_box, True, True, 0)

        self._toggle = Gtk.Switch()
        self._toggle.set_active(enabled)
        self._toggle.set_valign(Gtk.Align.CENTER)
        self._toggle.connect("state-set", lambda sw, state: on_toggle(mod_id, state))
        top.pack_start(self._toggle, False, False, 0)

        self.pack_start(top, False, False, 0)

        # Description
        desc = Gtk.Label(label=module_info["description"], xalign=0)
        desc.set_line_wrap(True)
        desc.set_lines(2)
        desc.set_ellipsize(3)
        desc.set_border_width(8)
        desc.get_style_context().add_class("dim-label")
        self.pack_start(desc, True, True, 0)

        # Launch button
        btn_bar = Gtk.Box()
        btn_bar.set_border_width(8)
        btn = Gtk.Button(label="Open")
        btn.connect("clicked", lambda b: on_launch(module_info))
        btn.set_hexpand(True)
        btn_bar.pack_start(btn, True, True, 0)
        self.pack_start(btn_bar, False, False, 0)

        # Make whole card clickable
        evbox = Gtk.EventBox()
        # Card border via CSS


class PowerToysApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="org.linux.powertoys",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._windows = {}  # module_id -> window instance

    def do_activate(self):
        win = self.get_active_window()
        if win is None:
            win = PowerToysMainWindow(application=self)
        win.present()


class PowerToysMainWindow(Gtk.ApplicationWindow):
    """Main PowerToys Settings window with sidebar and module cards."""

    def __init__(self, **kwargs):
        super().__init__(title=f"Linux PowerToys {__version__}", **kwargs)
        self.set_default_size(1100, 680)
        self.set_border_width(0)

        self._active_category = "All"
        self._search_query = ""
        self._module_windows = {}

        self._build_ui()
        self._apply_css()

    def _build_ui(self):
        # Header bar
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("Linux PowerToys")
        hb.set_subtitle(f"v{__version__}")
        self.set_titlebar(hb)

        # Search in header
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search modules…")
        self._search_entry.connect("search-changed", self._on_search)
        hb.pack_end(self._search_entry)

        # About button
        btn_about = Gtk.Button()
        btn_about.set_image(Gtk.Image.new_from_icon_name("help-about", Gtk.IconSize.BUTTON))
        btn_about.connect("clicked", self._on_about)
        hb.pack_end(btn_about)

        # Main layout: sidebar + content
        hpaned = Gtk.Box(spacing=0)
        self.add(hpaned)

        # Sidebar
        hpaned.pack_start(self._build_sidebar(), False, False, 0)
        hpaned.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)

        # Content area
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        hpaned.pack_start(self._content_box, True, True, 0)

        # Content header
        content_header = Gtk.Box(spacing=8)
        content_header.set_border_width(16)
        self._content_title = Gtk.Label(xalign=0)
        self._content_title.set_markup("<big><b>All Modules</b></big>")
        content_header.pack_start(self._content_title, True, True, 0)
        self._content_box.pack_start(content_header, False, False, 0)
        self._content_box.pack_start(Gtk.Separator(), False, False, 0)

        # Module grid in scrollable area
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._grid = Gtk.FlowBox()
        self._grid.set_valign(Gtk.Align.START)
        self._grid.set_max_children_per_line(4)
        self._grid.set_min_children_per_line(2)
        self._grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self._grid.set_row_spacing(12)
        self._grid.set_column_spacing(12)
        self._grid.set_border_width(16)

        scroll.add(self._grid)
        self._content_box.pack_start(scroll, True, True, 0)

        self._populate_modules()
        self.show_all()

    def _build_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_size_request(190, -1)

        # App logo area
        logo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        logo_box.set_border_width(16)
        logo = Gtk.Image.new_from_icon_name("applications-utilities", Gtk.IconSize.DIALOG)
        logo.set_pixel_size(48)
        logo_box.pack_start(logo, False, False, 0)
        title = Gtk.Label()
        title.set_markup("<b>Linux PowerToys</b>")
        logo_box.pack_start(title, False, False, 0)
        sidebar.pack_start(logo_box, False, False, 0)
        sidebar.pack_start(Gtk.Separator(), False, False, 0)

        # Category list
        lbl = Gtk.Label(label="CATEGORIES", xalign=0)
        lbl.set_border_width(8)
        lbl.get_style_context().add_class("dim-label")
        sidebar.pack_start(lbl, False, False, 0)

        self._cat_buttons = {}
        for cat in CATEGORIES:
            count = len([m for m in _MODULE_REGISTRY if cat == "All" or m["category"] == cat])
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_hexpand(True)

            box = Gtk.Box(spacing=8)
            box.set_border_width(4)
            lbl_cat = Gtk.Label(label=cat, xalign=0)
            lbl_cat.set_hexpand(True)
            box.pack_start(lbl_cat, True, True, 0)
            lbl_count = Gtk.Label(label=str(count))
            lbl_count.get_style_context().add_class("dim-label")
            box.pack_start(lbl_count, False, False, 0)
            btn.add(box)

            btn.connect("clicked", self._on_category_clicked, cat)
            self._cat_buttons[cat] = btn
            sidebar.pack_start(btn, False, False, 0)

        sidebar.pack_start(Gtk.Separator(), False, False, 4)

        # Settings link
        btn_settings = Gtk.Button(label="General Settings")
        btn_settings.set_relief(Gtk.ReliefStyle.NONE)
        btn_settings.connect("clicked", self._on_general_settings)
        sidebar.pack_start(btn_settings, False, False, 0)

        return sidebar

    def _populate_modules(self):
        for child in self._grid.get_children():
            self._grid.remove(child)

        for mod in _MODULE_REGISTRY:
            if self._active_category != "All" and mod["category"] != self._active_category:
                continue
            if self._search_query:
                q = self._search_query.lower()
                if q not in mod["name"].lower() and q not in mod["description"].lower():
                    continue

            card = ModuleCard(mod, self._on_launch_module, self._on_toggle_module)
            card.set_border_width(0)
            self._grid.add(card)

        self._grid.show_all()

        count = len(self._grid.get_children())
        title = self._active_category if self._active_category != "All" else "All Modules"
        if self._search_query:
            title = f'Search: \u201c{self._search_query}\u201d'
        self._content_title.set_markup(f"<big><b>{title}</b></big>  <span foreground='gray'>({count})</span>")

    def _on_category_clicked(self, btn, category: str):
        self._active_category = category
        self._populate_modules()

    def _on_search(self, entry):
        self._search_query = entry.get_text()
        self._active_category = "All"
        self._populate_modules()

    def _on_launch_module(self, module_info: dict):
        mod_id = module_info["id"]
        # Reuse existing window if open
        if mod_id in self._module_windows:
            win = self._module_windows[mod_id]
            if win.get_visible():
                win.present()
                return
            else:
                del self._module_windows[mod_id]

        # Lazy import and instantiate
        try:
            import importlib
            mod = importlib.import_module(module_info["module"])
            WinClass = getattr(mod, module_info["window_class"])
            win = WinClass(parent=self)
            win.connect("destroy", lambda w, mid=mod_id: self._module_windows.pop(mid, None))
            self._module_windows[mod_id] = win
            win.show_all()
        except Exception as e:
            dlg = Gtk.MessageDialog(
                parent=self, flags=0, message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"Failed to open {module_info['name']}",
            )
            dlg.format_secondary_text(str(e))
            dlg.run()
            dlg.destroy()

    def _on_toggle_module(self, mod_id: str, state: bool):
        config.set(f"modules.{mod_id}.enabled", state)

    def _on_general_settings(self, btn):
        self._launch_settings_dialog()

    def _launch_settings_dialog(self):
        dlg = Gtk.Dialog(title="General Settings", transient_for=self, modal=True)
        dlg.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        dlg.set_default_size(420, 280)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        grid.set_border_width(16)
        dlg.get_content_area().add(grid)

        row = 0
        grid.attach(Gtk.Label(label="Theme:", xalign=0), 0, row, 1, 1)
        theme_combo = Gtk.ComboBoxText()
        for t in ["System Default", "Light", "Dark"]:
            theme_combo.append_text(t)
        theme_combo.set_active(0)
        grid.attach(theme_combo, 1, row, 1, 1); row += 1

        start_check = Gtk.CheckButton(label="Launch at login")
        start_check.set_active(config.get("start_at_login", False))
        start_check.connect("toggled", lambda b: config.set("start_at_login", b.get_active()))
        grid.attach(start_check, 0, row, 2, 1); row += 1

        grid.attach(Gtk.Separator(), 0, row, 2, 1); row += 1
        grid.attach(Gtk.Label(label=f"Config file: {config.CONFIG_FILE}", xalign=0), 0, row, 2, 1); row += 1

        dlg.show_all()
        dlg.run()
        dlg.destroy()

    def _on_about(self, btn):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self)
        dlg.set_program_name("Linux PowerToys")
        dlg.set_version(__version__)
        dlg.set_comments("A Linux port of Microsoft PowerToys.\nProvides productivity utilities for Linux power users.")
        dlg.set_license_type(Gtk.License.MIT_X11)
        dlg.set_website("https://github.com/microsoft/PowerToys")
        dlg.set_authors(["Linux PowerToys Contributors", "Based on Microsoft PowerToys"])
        dlg.run()
        dlg.destroy()

    def _apply_css(self):
        css = b"""
        .module-card {
            border: 1px solid alpha(@borders, 0.5);
            border-radius: 8px;
            background-color: @theme_base_color;
        }
        .module-card:hover {
            border-color: @theme_selected_bg_color;
            background-color: alpha(@theme_selected_bg_color, 0.05);
        }
        """
        prov = Gtk.CssProvider()
        prov.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
