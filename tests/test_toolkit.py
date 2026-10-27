import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server
import toolkit
import recovery
import docker_gateway


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.destination = self.root / "recovery"
        self.destination.mkdir()
        self.oldroots = server.ROOTS
        server.ROOTS = {"host": self.source, "system": self.source}
        recovery.PLANS.clear()

    def tearDown(self):
        server.ROOTS = self.oldroots
        self.tmp.cleanup()

    def data(self, action, **kw):
        return {"action": action, "view": "host", "path": "/", **kw}

    def test_duplicate_content_and_not_just_size(self):
        for name, value in [("a", "abc"), ("b", "abc"), ("c", "xyz")]:
            (self.source / name).write_text(value)
        result = toolkit.run(server, self.data("duplicates"))
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["count"], 2)
        self.assertEqual(result["rows"][0]["bytes"], 3)

    def test_search_and_type_totals(self):
        (self.source / "a.PDF").write_text("abc")
        (self.source / "b.zip").write_text("other")
        result = toolkit.run(server, self.data("search", pattern="*.pdf"))
        self.assertEqual(result["rows"][0]["name"], "a.PDF")
        result = toolkit.run(server, self.data("types"))
        self.assertEqual(sum(r["bytes"] for r in result["rows"]), 8)

    def test_log_rules_and_secret_redaction(self):
        text = "ERROR no space left on device token=supersecret\nINFO Bisync successful"
        result = toolkit.analyze_log(text)
        self.assertEqual(len(result["rows"]), 2)
        self.assertNotIn("supersecret", str(result))
        self.assertIn("[VERBORGEN]", str(result))

    def test_docker_log_frames(self):
        frame = b"\x01\0\0\0" + (5).to_bytes(4, "big") + b"hello"
        self.assertEqual(docker_gateway.decode_logs(frame), "hello")

    def test_browse_metadata(self):
        (self.source / "folder").mkdir()
        (self.source / "data").write_text("abc")
        result = toolkit.browse(server, self.data("browse"))
        self.assertEqual(result["rows"][0]["kind"], "Ordner")
        self.assertEqual(result["rows"][1]["bytes"], 3)

    def test_copy_disabled_by_default(self):
        with patch.dict(os.environ, {"COPY_ENABLED": "0"}):
            with self.assertRaises(ValueError):
                recovery.run(server, self.data("copy_plan"))

    def test_copy_plan_rejects_unreadable_entries(self):
        with patch.dict(os.environ, {"COPY_ENABLED": "1"}), patch.object(server, "inventory", return_value=({}, 1, 0)):
            with self.assertRaises(ValueError):
                recovery.run(server, self.data("copy_plan"))

    def test_copy_requires_confirmation(self):
        with patch.dict(os.environ, {"COPY_ENABLED": "1"}):
            with self.assertRaises(ValueError):
                recovery.run(server, {"action": "copy_apply", "confirmation": "yes"})

    def test_copy_plan_hash_and_no_write(self):
        (self.source / "a").write_text("abc")
        with patch.dict(os.environ, {"COPY_ENABLED": "1"}):
            result = recovery.run(server, self.data("copy_plan"))
        self.assertIn("plan_id", result)
        self.assertEqual(list(self.destination.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "Descriptor-based copy requires Linux")
    def test_linux_copy_and_changed_source(self):
        (self.source / "sub").mkdir()
        (self.source / "sub" / "a").write_text("abc")
        with patch.dict(os.environ, {"COPY_ENABLED": "1", "RECOVERY_ROOT": str(self.destination)}):
            plan = recovery.run(server, self.data("copy_plan"))
            folder = recovery.PLANS[plan["plan_id"]]["folder"]
            recovery.run(server, {"action": "copy_apply", "plan_id": plan["plan_id"], "confirmation": "KOPIEREN"})
            self.assertEqual((self.destination / folder / "sub" / "a").read_text(), "abc")
            with self.assertRaises(ValueError):
                recovery.run(server, {"action": "copy_apply", "plan_id": plan["plan_id"], "confirmation": "KOPIEREN"})
            plan = recovery.run(server, self.data("copy_plan"))
            (self.source / "sub" / "a").write_text("changed")
            with self.assertRaises(ValueError):
                recovery.run(server, {"action": "copy_apply", "plan_id": plan["plan_id"], "confirmation": "KOPIEREN"})

    def test_cancel_checkpoint(self):
        server.JOBS["test"] = {"cancel": True}
        server.CONTEXT.job_id = "test"
        try:
            with self.assertRaises(InterruptedError):
                server.inventory(self.source)
            with self.assertRaises(InterruptedError):
                server.checkpoint()
        finally:
            server.CONTEXT.job_id = None
            del server.JOBS["test"]


if __name__ == "__main__":
    unittest.main()
