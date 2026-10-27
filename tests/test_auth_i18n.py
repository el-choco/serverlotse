import json
from pathlib import Path
import unittest
from unittest.mock import patch
import auth
import localization


class SessionTests(unittest.TestCase):
    def setUp(self):
        auth.REVOKED.clear()
        auth.ATTEMPTS.clear()
        self.token = "a-long-random-test-key-123456789"

    def test_valid_session_and_rotation(self):
        value, lifetime = auth.issue(self.token)
        self.assertTrue(auth.valid(value, self.token))
        self.assertFalse(auth.valid(value, self.token + "rotated"))
        self.assertNotIn(self.token, value)
        self.assertEqual(lifetime, 30 * 86400)

    def test_modified_and_expired_sessions_rejected(self):
        with patch.object(auth.time, "time", return_value=10000):
            value, _ = auth.issue(self.token, remember=False)
        self.assertFalse(auth.valid(value, self.token))
        value, _ = auth.issue(self.token)
        self.assertFalse(auth.valid(value + "x", self.token))
        self.assertFalse(auth.valid("bad.cookie.value", self.token))

    def test_logout_revokes_session(self):
        value, _ = auth.issue(self.token)
        auth.revoke(value)
        self.assertFalse(auth.valid(value, self.token))

    def test_cookie_flags_and_parsing(self):
        value, lifetime = auth.issue(self.token)
        cookie = auth.cookie(value, lifetime)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Secure", cookie)
        self.assertEqual(auth.from_header(auth.COOKIE + "=" + value), value)
        self.assertIn("Max-Age=0", auth.cookie("", 0))

    def test_login_rate_limit(self):
        self.assertTrue(all(auth.allow_attempt("test") for _ in range(10)))
        self.assertFalse(auth.allow_attempt("test"))


class LanguageTests(unittest.TestCase):
    def test_catalog_complete_and_unique(self):
        self.assertEqual(len(localization.CATALOG), len(localization.EXACT))
        for row in localization.CATALOG:
            self.assertEqual(len(row), 3)
            self.assertTrue(all(isinstance(value, str) and value for value in row))

    def test_languages_and_templates(self):
        self.assertEqual(localization.language("es-ES,en;q=0.5"), "es")
        self.assertEqual(localization.language("fr"), "de")
        self.assertEqual(localization.text("Ungültiger Zugangsschlüssel", "en"), "Invalid access key")
        self.assertEqual(localization.text("Vergleiche /mnt/Ordner", "es"), "Comparando /mnt/Ordner")

    def test_results_keep_file_names_and_evidence(self):
        body = {"action": "browse", "result": {"rows": [{"name": "Ordner", "kind": "Ordner"}], "note": "Nicht gefunden"}}
        result = localization.payload(body, "es")
        self.assertEqual(result["result"]["rows"][0]["name"], "Ordner")
        self.assertEqual(result["result"]["rows"][0]["kind"], "Ordner")
        self.assertEqual(result["result"]["note"], "No encontrado")
        result = localization.payload({"action": "log", "result": {"rows": [{"name": "Zugriff verweigert", "evidence": "Zugriff verweigert"}]}}, "en")
        self.assertEqual(result["result"]["rows"][0]["name"], "Access denied")
        self.assertEqual(result["result"]["rows"][0]["evidence"], "Zugriff verweigert")
