"""Tests for FancyZones engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from powertoys.modules.fancyzones.engine import (
    Zone, Layout, FancyZonesEngine, BUILTIN_LAYOUTS
)


class TestZone(unittest.TestCase):

    def test_to_pixels_full(self):
        zone = Zone(0, 0, 1.0, 1.0)
        x, y, w, h = zone.to_pixels(1920, 1080)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)

    def test_to_pixels_half_width(self):
        zone = Zone(0, 0, 0.5, 1.0)
        x, y, w, h = zone.to_pixels(1920, 1080)
        self.assertEqual(w, 960)

    def test_to_pixels_quarter(self):
        zone = Zone(0.25, 0.25, 0.5, 0.5)
        x, y, w, h = zone.to_pixels(1920, 1080)
        self.assertEqual(x, 480)
        self.assertEqual(y, 270)
        self.assertEqual(w, 960)
        self.assertEqual(h, 540)


class TestLayoutFactories(unittest.TestCase):

    def test_columns_2(self):
        layout = Layout.columns(2)
        self.assertEqual(len(layout.zones), 2)
        self.assertAlmostEqual(layout.zones[0].width, 0.5)
        self.assertAlmostEqual(layout.zones[1].x, 0.5)

    def test_columns_3(self):
        layout = Layout.columns(3)
        self.assertEqual(len(layout.zones), 3)
        for zone in layout.zones:
            self.assertAlmostEqual(zone.width, 1 / 3, places=5)

    def test_columns_4(self):
        layout = Layout.columns(4)
        self.assertEqual(len(layout.zones), 4)

    def test_rows_2(self):
        layout = Layout.rows(2)
        self.assertEqual(len(layout.zones), 2)
        self.assertAlmostEqual(layout.zones[0].height, 0.5)

    def test_grid_2x2(self):
        layout = Layout.grid(2, 2)
        self.assertEqual(len(layout.zones), 4)

    def test_grid_3x2(self):
        layout = Layout.grid(3, 2)
        self.assertEqual(len(layout.zones), 6)

    def test_primary_secondary_has_3_zones(self):
        layout = Layout.primary_secondary()
        self.assertEqual(len(layout.zones), 3)
        # Primary zone should be wider
        primary = layout.zones[0]
        self.assertGreater(primary.width, 0.5)

    def test_three_column_layout(self):
        layout = Layout.three_column()
        self.assertEqual(len(layout.zones), 3)
        # Center should be widest
        center = layout.zones[1]
        self.assertGreater(center.width, layout.zones[0].width)

    def test_full_screen_layout(self):
        layout = Layout(name="Full", zones=[Zone(0, 0, 1, 1, "Full")])
        x, y, w, h = layout.zones[0].to_pixels(1920, 1080)
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)

    def test_zones_cover_full_width(self):
        """All column layouts should cover the full screen width."""
        for n in [2, 3, 4]:
            layout = Layout.columns(n)
            total_w = sum(z.width for z in layout.zones)
            self.assertAlmostEqual(total_w, 1.0, places=5, msg=f"columns({n})")

    def test_zones_cover_full_height(self):
        """All row layouts should cover the full screen height."""
        for n in [2, 3]:
            layout = Layout.rows(n)
            total_h = sum(z.height for z in layout.zones)
            self.assertAlmostEqual(total_h, 1.0, places=5, msg=f"rows({n})")


class TestFancyZonesEngine(unittest.TestCase):

    def setUp(self):
        self.engine = FancyZonesEngine()

    def test_builtin_layouts_loaded(self):
        self.assertGreater(len(self.engine.layouts), 0)

    def test_activate_layout(self):
        layout = self.engine.layouts[0]
        self.engine.activate_layout(layout)
        self.assertEqual(self.engine.active_layout, layout)

    def test_add_custom_layout(self):
        n = len(self.engine.layouts)
        custom = Layout("My Custom", [Zone(0, 0, 0.3, 1), Zone(0.3, 0, 0.7, 1)])
        self.engine.add_custom_layout(custom)
        self.assertEqual(len(self.engine.layouts), n + 1)

    def test_remove_layout(self):
        custom = Layout("Removable", [Zone(0, 0, 1, 1)])
        self.engine.add_custom_layout(custom)
        self.engine.remove_layout("Removable")
        names = [l.name for l in self.engine.layouts]
        self.assertNotIn("Removable", names)

    def test_snap_without_active_layout(self):
        self.engine.active_layout = None
        result = self.engine.snap_active_window(0)
        self.assertFalse(result)

    def test_snap_invalid_zone_index(self):
        self.engine.activate_layout(Layout.columns(2))
        result = self.engine.snap_active_window(99)
        self.assertFalse(result)


class TestBuiltinLayouts(unittest.TestCase):

    def test_all_builtin_layouts_have_zones(self):
        for layout in BUILTIN_LAYOUTS:
            self.assertGreater(len(layout.zones), 0, f"{layout.name} has no zones")

    def test_all_builtin_layouts_have_names(self):
        for layout in BUILTIN_LAYOUTS:
            self.assertTrue(layout.name, f"Layout has empty name")

    def test_all_zones_in_bounds(self):
        for layout in BUILTIN_LAYOUTS:
            for zone in layout.zones:
                self.assertGreaterEqual(zone.x, 0, f"{layout.name}: zone x < 0")
                self.assertGreaterEqual(zone.y, 0, f"{layout.name}: zone y < 0")
                self.assertLessEqual(zone.x + zone.width, 1.01, f"{layout.name}: zone extends past right edge")
                self.assertLessEqual(zone.y + zone.height, 1.01, f"{layout.name}: zone extends past bottom edge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
