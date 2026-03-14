"""Tests for ImageResizer engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
import shutil
from pathlib import Path
from powertoys.modules.imageresizer.engine import (
    ImageResizerEngine, ResizePreset, DEFAULT_PRESETS,
    _compute_new_size, HAS_PILLOW
)


class TestComputeNewSize(unittest.TestCase):

    def test_fit_landscape(self):
        w, h = _compute_new_size(1920, 1080, 1280, 720, "Fit (keep aspect ratio)")
        self.assertEqual(w, 1280)
        self.assertEqual(h, 720)

    def test_fit_scales_down(self):
        w, h = _compute_new_size(4000, 3000, 1920, 1080, "Fit (keep aspect ratio)")
        self.assertLessEqual(w, 1920)
        self.assertLessEqual(h, 1080)
        # Aspect ratio preserved
        self.assertAlmostEqual(w / h, 4000 / 3000, places=1)

    def test_fill_exceeds_both_dims(self):
        w, h = _compute_new_size(1920, 1080, 500, 500, "Fill (crop to fit)")
        self.assertGreaterEqual(w, 500)
        self.assertGreaterEqual(h, 500)

    def test_stretch_ignores_aspect(self):
        w, h = _compute_new_size(1920, 1080, 100, 200, "Stretch (ignore aspect)")
        self.assertEqual(w, 100)
        self.assertEqual(h, 200)

    def test_width_only(self):
        w, h = _compute_new_size(1920, 1080, 960, 0, "Width only")
        self.assertEqual(w, 960)
        self.assertEqual(h, 540)  # half of 1080

    def test_height_only(self):
        w, h = _compute_new_size(1920, 1080, 0, 540, "Height only")
        self.assertEqual(h, 540)
        self.assertEqual(w, 960)


class TestResizePresets(unittest.TestCase):

    def test_default_presets_exist(self):
        names = [p.name for p in DEFAULT_PRESETS]
        self.assertIn("Small", names)
        self.assertIn("Medium", names)
        self.assertIn("Large", names)
        self.assertIn("Thumbnail", names)

    def test_preset_dimensions(self):
        medium = next(p for p in DEFAULT_PRESETS if p.name == "Medium")
        self.assertEqual(medium.width, 1280)
        self.assertEqual(medium.height, 720)

    def test_preset_str(self):
        p = ResizePreset("Test", 800, 600)
        self.assertIn("800", str(p))
        self.assertIn("600", str(p))


@unittest.skipUnless(HAS_PILLOW, "Pillow not available")
class TestImageResizerEngine(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self._create_test_image()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_test_image(self):
        from PIL import Image
        self.test_img = self.tmpdir / "test.png"
        img = Image.new("RGB", (800, 600), color=(255, 128, 0))
        img.save(self.test_img)

    def test_resize_to_preset(self):
        preset = ResizePreset("Small", 200, 150)
        engine = ImageResizerEngine(preset=preset, output_suffix="_small")
        result = engine.resize_image(self.test_img)
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.output.exists())
        self.assertEqual(result.new_size, (200, 150))

    def test_resize_fit_preserves_aspect(self):
        preset = ResizePreset("Wide", 400, 400, "Fit (keep aspect ratio)")
        engine = ImageResizerEngine(preset=preset, output_suffix="_wide")
        result = engine.resize_image(self.test_img)
        self.assertTrue(result.success, result.error)
        w, h = result.new_size
        # Original 800x600 = 4:3, fitting 400x400 → 400x300
        self.assertEqual(w, 400)
        self.assertEqual(h, 300)

    def test_resize_fill_crops(self):
        preset = ResizePreset("Square", 200, 200, "Fill (crop to fit)")
        engine = ImageResizerEngine(preset=preset, output_suffix="_sq")
        result = engine.resize_image(self.test_img)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.new_size, (200, 200))

    def test_output_suffix_applied(self):
        preset = ResizePreset("Test", 100, 100)
        engine = ImageResizerEngine(preset=preset, output_suffix="_thumb")
        result = engine.resize_image(self.test_img)
        self.assertIn("_thumb", result.output.name)

    def test_custom_output_dir(self):
        out_dir = self.tmpdir / "output"
        out_dir.mkdir()
        preset = ResizePreset("Test", 100, 100)
        engine = ImageResizerEngine(preset=preset, output_dir=str(out_dir), output_suffix="_out")
        result = engine.resize_image(self.test_img)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output.parent, out_dir)

    def test_unsupported_format_returns_error(self):
        bad = self.tmpdir / "file.xyz"
        bad.touch()
        engine = ImageResizerEngine(preset=DEFAULT_PRESETS[0], output_suffix="_x")
        result = engine.resize_image(bad)
        self.assertFalse(result.success)
        self.assertIn("Unsupported", result.error)

    def test_batch_resize(self):
        from PIL import Image
        paths = []
        for i in range(3):
            p = self.tmpdir / f"img_{i}.png"
            Image.new("RGB", (100, 100), (i * 80, 0, 0)).save(p)
            paths.append(p)

        preset = ResizePreset("Tiny", 50, 50)
        engine = ImageResizerEngine(preset=preset, output_suffix="_tiny")
        results = engine.resize_batch(paths)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))

    def test_jpeg_conversion(self):
        engine = ImageResizerEngine(
            preset=DEFAULT_PRESETS[0], output_suffix="_j", output_format="jpg"
        )
        result = engine.resize_image(self.test_img)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output.suffix.lower(), ".jpg")

    def test_progress_callback(self):
        from PIL import Image
        paths = [self.tmpdir / f"cb_{i}.png" for i in range(2)]
        for p in paths:
            Image.new("RGB", (100, 100)).save(p)

        calls = []
        preset = ResizePreset("T", 50, 50)
        engine = ImageResizerEngine(preset=preset, output_suffix="_p")
        engine.resize_batch(paths, progress_cb=lambda done, total, r: calls.append((done, total)))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1], (2, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
