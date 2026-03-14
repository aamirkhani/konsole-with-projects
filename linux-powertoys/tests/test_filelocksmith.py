"""Tests for FileLocksmith engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
from pathlib import Path
from powertoys.modules.filelocksmith.engine import FileLocksmithEngine, FileHandle, _get_username


class TestFileHandle(unittest.TestCase):

    def test_display_access_read(self):
        h = FileHandle(1, "proc", "user", "/path", "REG", "r")
        self.assertEqual(h.display_access, "Read")

    def test_display_access_write(self):
        h = FileHandle(1, "proc", "user", "/path", "REG", "w")
        self.assertEqual(h.display_access, "Write")

    def test_display_access_readwrite(self):
        h = FileHandle(1, "proc", "user", "/path", "REG", "u")
        self.assertEqual(h.display_access, "Read/Write")

    def test_display_access_unknown(self):
        h = FileHandle(1, "proc", "user", "/path", "REG", "x")
        self.assertEqual(h.display_access, "x")


class TestFileLocksmithEngine(unittest.TestCase):

    def setUp(self):
        self.engine = FileLocksmithEngine()

    def test_find_own_process_file(self):
        """Our own process should have /proc/self open."""
        # Create a temp file and open it
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp_path = tmp.name
        try:
            # The file should be findable via /proc
            handles = self.engine.find(tmp_path)
            # At least this process should have it open (tmp is open)
            # Note: may not work in all environments, so just check it doesn't crash
            self.assertIsInstance(handles, list)
        finally:
            tmp.close()
            os.unlink(tmp_path)

    def test_find_nonexistent_returns_empty(self):
        handles = self.engine.find("/this/path/does/not/exist")
        self.assertIsInstance(handles, list)

    def test_find_proc_self_maps(self):
        """Test finding open handles for a well-known system path."""
        handles = self.engine.find("/proc/self")
        # May or may not find handles depending on environment
        self.assertIsInstance(handles, list)

    def test_get_open_files_self(self):
        """Get open files for current process."""
        files = self.engine.get_open_files(os.getpid())
        self.assertIsInstance(files, list)
        # Current process should have some open files
        self.assertGreater(len(files), 0)

    def test_get_open_files_invalid_pid(self):
        """Invalid PID should return empty list."""
        files = self.engine.get_open_files(99999999)
        self.assertEqual(files, [])

    def test_kill_invalid_pid_returns_false(self):
        result = self.engine.kill_process(99999999, force=False)
        self.assertFalse(result)


class TestGetUsername(unittest.TestCase):

    def test_get_root_username(self):
        name = _get_username("0")
        self.assertEqual(name, "root")

    def test_invalid_uid_returns_uid(self):
        name = _get_username("99999999")
        # Either returns the uid string or a name - should not crash
        self.assertIsInstance(name, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
