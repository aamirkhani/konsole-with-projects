"""Tests for ColorPicker engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from powertoys.modules.colorpicker.picker import ColorPickerEngine


class TestColorConversions(unittest.TestCase):

    def setUp(self):
        self.engine = ColorPickerEngine()

    # ── HEX ──────────────────────────────────────────────────────────────

    def test_rgb_to_hex_white(self):
        self.assertEqual(self.engine.rgb_to_hex(255, 255, 255), "#FFFFFF")

    def test_rgb_to_hex_black(self):
        self.assertEqual(self.engine.rgb_to_hex(0, 0, 0), "#000000")

    def test_rgb_to_hex_red(self):
        self.assertEqual(self.engine.rgb_to_hex(255, 0, 0), "#FF0000")

    def test_hex_to_rgb_white(self):
        self.assertEqual(self.engine.hex_to_rgb("#FFFFFF"), (255, 255, 255))

    def test_hex_to_rgb_black(self):
        self.assertEqual(self.engine.hex_to_rgb("#000000"), (0, 0, 0))

    def test_hex_to_rgb_shorthand(self):
        self.assertEqual(self.engine.hex_to_rgb("#FFF"), (255, 255, 255))

    def test_hex_to_rgb_lowercase(self):
        r, g, b = self.engine.hex_to_rgb("#ff0000")
        self.assertEqual((r, g, b), (255, 0, 0))

    def test_hex_roundtrip(self):
        for r, g, b in [(0, 0, 0), (255, 255, 255), (123, 45, 67), (0, 128, 255)]:
            hex_val = self.engine.rgb_to_hex(r, g, b)
            r2, g2, b2 = self.engine.hex_to_rgb(hex_val)
            self.assertEqual((r, g, b), (r2, g2, b2))

    # ── HSL ──────────────────────────────────────────────────────────────

    def test_hsl_red(self):
        h, s, l = self.engine.rgb_to_hsl(255, 0, 0)
        self.assertAlmostEqual(h, 0.0, places=0)
        self.assertAlmostEqual(s, 100.0, places=0)
        self.assertAlmostEqual(l, 50.0, places=0)

    def test_hsl_white(self):
        h, s, l = self.engine.rgb_to_hsl(255, 255, 255)
        self.assertAlmostEqual(s, 0.0, places=0)
        self.assertAlmostEqual(l, 100.0, places=0)

    def test_hsl_black(self):
        h, s, l = self.engine.rgb_to_hsl(0, 0, 0)
        self.assertAlmostEqual(l, 0.0, places=0)

    def test_hsl_green(self):
        h, s, l = self.engine.rgb_to_hsl(0, 255, 0)
        self.assertAlmostEqual(h, 120.0, places=0)

    def test_hsl_blue(self):
        h, s, l = self.engine.rgb_to_hsl(0, 0, 255)
        self.assertAlmostEqual(h, 240.0, places=0)

    # ── HSV ──────────────────────────────────────────────────────────────

    def test_hsv_red(self):
        h, s, v = self.engine.rgb_to_hsv(255, 0, 0)
        self.assertAlmostEqual(h, 0.0, places=0)
        self.assertAlmostEqual(s, 100.0, places=0)
        self.assertAlmostEqual(v, 100.0, places=0)

    def test_hsv_black(self):
        h, s, v = self.engine.rgb_to_hsv(0, 0, 0)
        self.assertAlmostEqual(v, 0.0, places=0)

    # ── CMYK ─────────────────────────────────────────────────────────────

    def test_cmyk_black(self):
        c, m, y, k = self.engine.rgb_to_cmyk(0, 0, 0)
        self.assertAlmostEqual(k, 100.0, places=0)

    def test_cmyk_white(self):
        c, m, y, k = self.engine.rgb_to_cmyk(255, 255, 255)
        self.assertAlmostEqual(k, 0.0, places=0)
        self.assertAlmostEqual(c, 0.0, places=0)

    def test_cmyk_red(self):
        c, m, y, k = self.engine.rgb_to_cmyk(255, 0, 0)
        self.assertAlmostEqual(m, 100.0, places=0)
        self.assertAlmostEqual(c, 0.0, places=0)

    # ── Format output ─────────────────────────────────────────────────────

    def test_format_hex(self):
        result = self.engine.format_color(255, 0, 0, "HEX")
        self.assertEqual(result, "#FF0000")

    def test_format_rgb(self):
        result = self.engine.format_color(100, 150, 200, "RGB")
        self.assertIn("100", result)
        self.assertIn("150", result)
        self.assertIn("200", result)

    def test_format_hsl(self):
        result = self.engine.format_color(255, 0, 0, "HSL")
        self.assertIn("hsl", result)

    def test_format_cmyk(self):
        result = self.engine.format_color(255, 0, 0, "CMYK")
        self.assertIn("cmyk", result)

    def test_format_decimal(self):
        result = self.engine.format_color(0, 0, 255, "Decimal")
        self.assertEqual(result, str(255))  # 0*65536 + 0*256 + 255

    def test_format_decimal_blue(self):
        result = self.engine.format_color(0, 1, 0, "Decimal")
        self.assertEqual(result, str(256))

    def test_all_formats_available(self):
        for fmt in ColorPickerEngine.FORMATS:
            result = self.engine.format_color(128, 64, 32, fmt)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
