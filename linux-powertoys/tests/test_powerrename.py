"""Tests for PowerRename engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
import shutil
from pathlib import Path
from powertoys.modules.powerrename.engine import PowerRenameEngine, CASE_TRANSFORMS


class TestPowerRenameBasic(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_files(self, names):
        paths = []
        for name in names:
            p = self.tmpdir / name
            p.touch()
            paths.append(p)
        return paths

    # ── Search/Replace ───────────────────────────────────────────────────

    def test_simple_replace(self):
        paths = self._make_files(["hello_world.txt", "hello_foo.txt"])
        engine = PowerRenameEngine(search="hello", replace="goodbye")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "goodbye_world.txt")
        self.assertEqual(results[1].new_name, "goodbye_foo.txt")

    def test_case_insensitive_replace(self):
        paths = self._make_files(["Hello.txt", "HELLO.txt", "hello.txt"])
        engine = PowerRenameEngine(search="hello", replace="hi", case_sensitive=False)
        results = engine.preview(paths)
        for r in results:
            self.assertEqual(r.new_name, "hi.txt")

    def test_case_sensitive_replace(self):
        paths = self._make_files(["Hello.txt", "hello.txt"])
        engine = PowerRenameEngine(search="hello", replace="bye", case_sensitive=True)
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "Hello.txt")  # no change
        self.assertEqual(results[1].new_name, "bye.txt")

    def test_no_search_no_change(self):
        paths = self._make_files(["file.txt"])
        engine = PowerRenameEngine(search="", replace="")
        results = engine.preview(paths)
        self.assertFalse(results[0].changed)

    def test_replace_removes_text(self):
        paths = self._make_files(["copy_of_document.pdf"])
        engine = PowerRenameEngine(search="copy_of_", replace="")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "document.pdf")

    # ── Regex ────────────────────────────────────────────────────────────

    def test_regex_replace(self):
        paths = self._make_files(["img001.jpg", "img002.jpg", "img100.jpg"])
        engine = PowerRenameEngine(search=r"img(\d+)", replace=r"photo_\1", use_regex=True)
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "photo_001.jpg")
        self.assertEqual(results[1].new_name, "photo_002.jpg")
        self.assertEqual(results[2].new_name, "photo_100.jpg")

    def test_regex_strip_leading_numbers(self):
        paths = self._make_files(["01_intro.txt", "02_main.txt", "10_end.txt"])
        engine = PowerRenameEngine(search=r"^\d+_", replace="", use_regex=True)
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "intro.txt")
        self.assertEqual(results[1].new_name, "main.txt")
        self.assertEqual(results[2].new_name, "end.txt")

    def test_invalid_regex_returns_error(self):
        paths = self._make_files(["file.txt"])
        engine = PowerRenameEngine(search="[invalid(", replace="x", use_regex=True)
        results = engine.preview(paths)
        self.assertIsNotNone(results[0].error)

    # ── Case Transform ───────────────────────────────────────────────────

    def test_uppercase_transform(self):
        paths = self._make_files(["hello world.txt"])
        engine = PowerRenameEngine(case_transform="UPPERCASE")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "HELLO WORLD.txt")

    def test_lowercase_transform(self):
        paths = self._make_files(["HELLO.txt", "MiXeD.txt"])
        engine = PowerRenameEngine(case_transform="lowercase")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "hello.txt")
        self.assertEqual(results[1].new_name, "mixed.txt")

    def test_title_case_transform(self):
        paths = self._make_files(["hello world.txt"])
        engine = PowerRenameEngine(case_transform="Title Case")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "Hello World.txt")

    def test_snake_case_transform(self):
        paths = self._make_files(["Hello World File.txt"])
        engine = PowerRenameEngine(case_transform="snake_case")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "hello_world_file.txt")

    def test_kebab_case_transform(self):
        paths = self._make_files(["Hello World.txt"])
        engine = PowerRenameEngine(case_transform="kebab-case")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "hello-world.txt")

    # ── Extension handling ────────────────────────────────────────────────

    def test_extension_not_changed_by_default(self):
        paths = self._make_files(["document.TXT"])
        engine = PowerRenameEngine(case_transform="lowercase")
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "document.TXT")  # ext unchanged

    def test_apply_to_extension(self):
        paths = self._make_files(["document.TXT"])
        engine = PowerRenameEngine(case_transform="lowercase", apply_to_extension=True)
        results = engine.preview(paths)
        self.assertEqual(results[0].new_name, "document.txt")

    # ── Enumeration ───────────────────────────────────────────────────────

    def test_enumerate_basic(self):
        paths = self._make_files(["photo.jpg", "photo2.jpg", "photo3.jpg"])
        engine = PowerRenameEngine(enumerate_files=True, enum_start=1, enum_separator="_")
        results = engine.preview(paths)
        self.assertTrue(results[0].new_name.endswith("_1.jpg"))
        self.assertTrue(results[1].new_name.endswith("_2.jpg"))
        self.assertTrue(results[2].new_name.endswith("_3.jpg"))

    def test_enumerate_with_padding(self):
        paths = self._make_files(["a.jpg", "b.jpg"])
        engine = PowerRenameEngine(enumerate_files=True, enum_start=1, enum_padding=3)
        results = engine.preview(paths)
        self.assertTrue("001" in results[0].new_name)
        self.assertTrue("002" in results[1].new_name)

    def test_enumerate_with_custom_start(self):
        paths = self._make_files(["img.jpg"])
        engine = PowerRenameEngine(enumerate_files=True, enum_start=10)
        results = engine.preview(paths)
        self.assertTrue("10" in results[0].new_name)

    # ── Apply (real rename) ───────────────────────────────────────────────

    def test_apply_renames_files(self):
        paths = self._make_files(["old_name.txt"])
        engine = PowerRenameEngine(search="old", replace="new")
        results = engine.apply(paths)
        self.assertTrue(results[0].success)
        self.assertTrue((self.tmpdir / "new_name.txt").exists())
        self.assertFalse((self.tmpdir / "old_name.txt").exists())

    def test_apply_preserves_unchanged(self):
        paths = self._make_files(["unchanged.txt"])
        engine = PowerRenameEngine(search="xyz", replace="abc")
        results = engine.apply(paths)
        self.assertTrue(results[0].success)
        self.assertTrue((self.tmpdir / "unchanged.txt").exists())

    def test_apply_detects_collision(self):
        paths = self._make_files(["a.txt", "b.txt"])
        (self.tmpdir / "b.txt").unlink()  # remove b, but rename a -> b
        (self.tmpdir / "b.txt").touch()   # create b again
        paths = self._make_files(["a.txt"])
        engine = PowerRenameEngine(search="a", replace="b")
        results = engine.preview(paths)
        self.assertIsNotNone(results[0].error)  # collision detected

    # ── Directory scanning ────────────────────────────────────────────────

    def test_scan_directory(self):
        (self.tmpdir / "sub").mkdir()
        (self.tmpdir / "file1.txt").touch()
        (self.tmpdir / "file2.txt").touch()
        (self.tmpdir / "sub" / "file3.txt").touch()

        engine = PowerRenameEngine()
        paths = engine.scan_directory(str(self.tmpdir))
        names = [p.name for p in paths]
        self.assertIn("file1.txt", names)
        self.assertIn("file2.txt", names)
        self.assertNotIn("file3.txt", names)  # not recursive

    def test_scan_directory_recursive(self):
        (self.tmpdir / "sub").mkdir()
        (self.tmpdir / "file1.txt").touch()
        (self.tmpdir / "sub" / "file3.txt").touch()

        engine = PowerRenameEngine()
        paths = engine.scan_directory(str(self.tmpdir), recursive=True)
        names = [p.name for p in paths]
        self.assertIn("file1.txt", names)
        self.assertIn("file3.txt", names)


class TestCaseTransforms(unittest.TestCase):
    def test_all_transforms_available(self):
        expected = {"None", "UPPERCASE", "lowercase", "Title Case", "snake_case", "kebab-case", "camelCase", "PascalCase"}
        self.assertTrue(expected.issubset(set(CASE_TRANSFORMS.keys())))

    def test_none_transform_returns_identity(self):
        fn = CASE_TRANSFORMS["None"]
        self.assertIsNone(fn)

    def test_camel_case(self):
        fn = CASE_TRANSFORMS["camelCase"]
        self.assertEqual(fn("Hello World"), "helloWorld")

    def test_pascal_case(self):
        fn = CASE_TRANSFORMS["PascalCase"]
        result = fn("hello world")
        self.assertTrue(result[0].isupper())


if __name__ == "__main__":
    unittest.main(verbosity=2)
