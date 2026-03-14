"""Tests for configuration management."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch


class TestConfig(unittest.TestCase):

    def setUp(self):
        # Use a temp directory for config
        self.tmpdir = tempfile.mkdtemp()
        self.config_file = Path(self.tmpdir) / "settings.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _get_patched_config(self):
        """Get config module with patched paths."""
        import importlib
        import powertoys.config as cfg_module
        # Patch the config file path
        cfg_module.CONFIG_DIR = Path(self.tmpdir)
        cfg_module.CONFIG_FILE = self.config_file
        return cfg_module

    def test_load_returns_defaults_when_no_file(self):
        cfg = self._get_patched_config()
        config = cfg.load()
        self.assertIn("theme", config)
        self.assertIn("modules", config)
        self.assertIn("powerrename", config["modules"])

    def test_save_creates_file(self):
        cfg = self._get_patched_config()
        data = cfg.load()
        cfg.save(data)
        self.assertTrue(self.config_file.exists())

    def test_save_and_load_roundtrip(self):
        cfg = self._get_patched_config()
        data = cfg.load()
        data["theme"] = "dark"
        cfg.save(data)
        data2 = cfg.load()
        self.assertEqual(data2["theme"], "dark")

    def test_get_dotted_key(self):
        cfg = self._get_patched_config()
        data = cfg.load()
        data["modules"]["awake"]["enabled"] = False
        cfg.save(data)
        val = cfg.get("modules.awake.enabled")
        self.assertFalse(val)

    def test_get_missing_key_returns_default(self):
        cfg = self._get_patched_config()
        val = cfg.get("nonexistent.key.deep", "fallback")
        self.assertEqual(val, "fallback")

    def test_set_dotted_key(self):
        cfg = self._get_patched_config()
        cfg.set("modules.colorpicker.format", "rgb")
        val = cfg.get("modules.colorpicker.format")
        self.assertEqual(val, "rgb")

    def test_corrupt_json_falls_back_to_defaults(self):
        self.config_file.write_text("{invalid json}")
        cfg = self._get_patched_config()
        config = cfg.load()
        self.assertIn("theme", config)  # Should still have defaults


class TestClipboardHistory(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_retrieve_entry(self):
        from powertoys.modules.clipboard.history import ClipboardEngine, ClipboardEntry
        engine = ClipboardEngine(max_items=10)
        engine.history.clear()
        entry = ClipboardEntry(content="test content")
        engine.history.insert(0, entry)
        self.assertEqual(len(engine.history), 1)
        self.assertEqual(engine.history[0].content, "test content")

    def test_max_items_enforced(self):
        from powertoys.modules.clipboard.history import ClipboardEngine, ClipboardEntry
        engine = ClipboardEngine(max_items=3)
        engine.history.clear()
        for i in range(5):
            engine._add_entry(f"item {i}")
        unpinned = [e for e in engine.history if not e.pinned]
        self.assertLessEqual(len(unpinned), 3)

    def test_pinned_entry_not_removed(self):
        from powertoys.modules.clipboard.history import ClipboardEngine, ClipboardEntry
        engine = ClipboardEngine(max_items=2)
        engine.history.clear()
        pinned = ClipboardEntry(content="pinned!", pinned=True)
        engine.history.append(pinned)
        for i in range(5):
            engine._add_entry(f"item {i}")
        # Pinned entry should still be there
        self.assertTrue(any(e.content == "pinned!" for e in engine.history))

    def test_search_entries(self):
        from powertoys.modules.clipboard.history import ClipboardEngine, ClipboardEntry
        engine = ClipboardEngine()
        engine.history.clear()
        engine.history.append(ClipboardEntry(content="hello world"))
        engine.history.append(ClipboardEntry(content="foo bar"))
        results = engine.search("hello")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "hello world")

    def test_clear_keeps_pinned(self):
        from powertoys.modules.clipboard.history import ClipboardEngine, ClipboardEntry
        engine = ClipboardEngine()
        engine.history.clear()
        engine.history.append(ClipboardEntry(content="pinned", pinned=True))
        engine.history.append(ClipboardEntry(content="not pinned"))
        engine.clear_history(keep_pinned=True)
        self.assertEqual(len(engine.history), 1)
        self.assertEqual(engine.history[0].content, "pinned")

    def test_entry_preview_truncates(self):
        from powertoys.modules.clipboard.history import ClipboardEntry
        long = "x" * 200
        entry = ClipboardEntry(content=long)
        self.assertLessEqual(len(entry.preview), 85)

    def test_entry_multiline_preview(self):
        from powertoys.modules.clipboard.history import ClipboardEntry
        entry = ClipboardEntry(content="line1\nline2\nline3")
        self.assertIn("3 lines", entry.preview)


class TestScreenRulerEngine(unittest.TestCase):

    def test_convert_pixels(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine(dpi=96)
        result = engine.convert(96, "Pixels")
        self.assertEqual(result, "96 px")

    def test_convert_inches(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine(dpi=96)
        result = engine.convert(96, "Inches")
        self.assertIn("1.000", result)
        self.assertIn("in", result)

    def test_convert_cm(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine(dpi=96)
        result = engine.convert(96, "Centimeters")
        self.assertIn("cm", result)

    def test_convert_points(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine(dpi=96)
        result = engine.convert(96, "Points (pt)")
        self.assertIn("pt", result)

    def test_pixels_between(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine()
        dist = engine.pixels_between(0, 0, 3, 4)
        self.assertAlmostEqual(dist, 5.0, places=5)

    def test_pixels_between_horizontal(self):
        from powertoys.modules.screenruler.ruler import ScreenRulerEngine
        engine = ScreenRulerEngine()
        dist = engine.pixels_between(0, 0, 100, 0)
        self.assertEqual(dist, 100.0)


class TestAwakeEngine(unittest.TestCase):

    def test_initial_state_inactive(self):
        from powertoys.modules.awake.awake import AwakeEngine
        engine = AwakeEngine()
        self.assertFalse(engine.active)

    def test_start_sets_active(self):
        from powertoys.modules.awake.awake import AwakeEngine
        engine = AwakeEngine()
        engine.start()
        self.assertTrue(engine.active)
        engine.stop()

    def test_stop_clears_active(self):
        from powertoys.modules.awake.awake import AwakeEngine
        engine = AwakeEngine()
        engine.start()
        engine.stop()
        self.assertFalse(engine.active)

    def test_double_start_safe(self):
        from powertoys.modules.awake.awake import AwakeEngine
        engine = AwakeEngine()
        engine.start()
        engine.start()  # Should not raise
        self.assertTrue(engine.active)
        engine.stop()

    def test_stop_without_start_safe(self):
        from powertoys.modules.awake.awake import AwakeEngine
        engine = AwakeEngine()
        engine.stop()  # Should not raise


class TestKeyboardEngine(unittest.TestCase):

    def test_load_creates_empty_remaps(self):
        from powertoys.modules.keyboard.manager import KeyboardEngine
        engine = KeyboardEngine()
        self.assertIsInstance(engine.key_remaps, list)
        self.assertIsInstance(engine.shortcut_remaps, list)

    def test_keyd_config_generated(self):
        from powertoys.modules.keyboard.manager import KeyboardEngine, KeyRemap
        engine = KeyboardEngine()
        engine.key_remaps = [KeyRemap(from_key="CapsLock", to_key="Escape")]
        config = engine.generate_keyd_config()
        self.assertIn("[main]", config)
        self.assertIn("capslock", config.lower())
        self.assertIn("escape", config.lower())

    def test_keyd_config_respects_enabled(self):
        from powertoys.modules.keyboard.manager import KeyboardEngine, KeyRemap
        engine = KeyboardEngine()
        engine.key_remaps = [
            KeyRemap(from_key="A", to_key="B", enabled=True),
            KeyRemap(from_key="C", to_key="D", enabled=False),
        ]
        config = engine.generate_keyd_config()
        self.assertNotIn("c = d", config.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
