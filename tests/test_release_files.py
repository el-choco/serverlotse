from pathlib import Path
import unittest


class ReleaseFileTests(unittest.TestCase):
    def test_host_scripts_use_unix_line_endings(self):
        root=Path(__file__).resolve().parent.parent
        for pattern in ('*.sh','*.service'):
            for path in root.glob(pattern):
                with self.subTest(file=path.name):
                    self.assertNotIn(b'\r',path.read_bytes())
                    self.assertTrue(path.read_bytes().endswith(b'\n'))
