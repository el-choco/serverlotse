from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server
import toolkit


class FolderPickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)
        self.roots = patch.object(server, "ROOTS", {"host": self.root, "system": self.root})
        self.roots.start()

    def tearDown(self):
        self.roots.stop()
        self.tmp.cleanup()

    def test_only_directories_including_hidden_and_sorted(self):
        (self.root / "Zebra").mkdir()
        (self.root / "alpha").mkdir()
        (self.root / ".cache").mkdir()
        (self.root / "file.txt").write_text("ignored")
        result = toolkit.folders(server, "host", "/")
        self.assertEqual(result["folders"], [".cache", "alpha", "Zebra"])
        self.assertEqual(result["errors"], 0)

    def test_nested_folder_and_view(self):
        (self.root / "a").mkdir()
        (self.root / "a" / "b").mkdir()
        result = toolkit.folders(server, "system", "/a")
        self.assertEqual(result["folders"], ["b"])
        self.assertEqual(result["view"], "system")

    def test_invalid_paths_and_views_rejected(self):
        for view, path in [("host", "/../"), ("outside", "/"), ("host", "/missing")]:
            with self.subTest(view=view, path=path), self.assertRaises(ValueError):
                toolkit.folders(server, view, path)
