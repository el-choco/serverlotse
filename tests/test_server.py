import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("server", Path(__file__).parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.base = Path(self.tmp.name)
        self.a = self.base / "a"
        self.b = self.base / "b"
        self.a.mkdir()
        self.b.mkdir()
        server.ROOTS = {"system": self.a, "host": self.b}

    def tearDown(self):
        self.tmp.cleanup()

    def test_comparison_reads_content_not_only_size(self):
        for name, a, b in [("same", b"abc", b"abc"), ("changed", b"abc", b"xyz")]:
            (self.a / name).write_bytes(a)
            (self.b / name).write_bytes(b)
        (self.a / "missing").write_text("recover me")
        (self.b / "extra").write_text("keep me")
        result = server.compare("system", "/", "host", "/")
        self.assertEqual(result["counts"], {"same": 1, "missing": 1, "different": 1, "error": 0})
        self.assertEqual((self.b / "changed").read_bytes(), b"xyz")
        self.assertFalse((self.b / "missing").exists())

    def test_path_escape_is_rejected(self):
        for path in ["/../a", "relative", "/x/../../b", "/a\\b"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                server.resolve_path("system", path)

    def test_symlink_escape_is_rejected(self):
        try:
            (self.a / "escape").symlink_to(self.b, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaises(ValueError):
            server.resolve_path("system", "/escape")

    def test_hidden_files_are_included_and_hardlinks_count_once(self):
        (self.a / ".hidden").mkdir()
        original = self.a / ".hidden" / "data"
        original.write_bytes(b"x" * 10000)
        try:
            os.link(original, self.a / "alias")
        except OSError:
            self.skipTest("Hardlinks unavailable")
        result = server.scan("system", "/")
        info = original.stat()
        expected = info.st_blocks * 512 if hasattr(info, "st_blocks") else info.st_size
        self.assertEqual(result["bytes"], expected)
        self.assertEqual(result["files"], 2)

    def test_hidden_files_are_included_without_hardlinks(self):
        (self.a / ".private").mkdir()
        (self.a / ".private" / "data").write_text("hello")
        result = server.scan("system", "/")
        self.assertEqual(result["files"], 1)
        self.assertEqual(result["errors"], 0)

    def test_permission_errors_prevent_complete_verification(self):
        with patch.object(server, "inventory", return_value=({}, 1, 0)):
            result = server.compare("system", "/", "host", "/")
        self.assertFalse(result["complete"])
        self.assertEqual(result["errors"], 1)

    def test_auth_requires_exact_key_outside_demo(self):
        handler = object.__new__(server.Handler)
        with patch.object(server, "DEMO", False), patch.object(server, "TOKEN", "x" * 32):
            handler.headers = {}
            self.assertFalse(handler.authorized())
            handler.headers = {"Authorization": "Bearer wrong"}
            self.assertFalse(handler.authorized())
            handler.headers = {"Authorization": "Bearer " + "x" * 32}
            self.assertTrue(handler.authorized())

    def test_target_symlink_never_followed(self):
        (self.a / "file").write_text("hello")
        try:
            (self.b / "file").symlink_to(self.a / "file")
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        result = server.compare("system", "/", "host", "/")
        self.assertEqual(result["counts"]["error"], 1)
        self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
