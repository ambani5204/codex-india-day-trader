"""Synthetic tests; never use real credentials or network."""
import io
import os
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest.mock import patch
from deploy import phase0_github_auth_probe as probe

class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False

class ProbeTests(unittest.TestCase):
    def test_http_200(self):
        self.assertEqual(probe.status("dummy", "/user", opener=lambda req, timeout: Response()), 200)

    def test_http_404_is_reported_without_body(self):
        def missing(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 404, "private detail", {}, io.BytesIO(b"secret response"))
        self.assertEqual(probe.status("dummy", "/user", opener=missing), 404)

    def test_missing_secret_fails_closed(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"JOURNAL_REPO_TOKEN": ""}), redirect_stdout(output):
            self.assertEqual(probe.main(), 2)
        self.assertIn("SECRET_MISSING", output.getvalue())

    def test_mixed_status_fails_closed_without_leaking_token(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"JOURNAL_REPO_TOKEN": "sensitive-example"}), patch.object(probe, "status", side_effect=[200, 404]), redirect_stdout(output):
            self.assertEqual(probe.main(), 4)
        self.assertIn("PRIVATE_REPO http_status=404", output.getvalue())
        self.assertNotIn("sensitive-example", output.getvalue())

if __name__ == "__main__":
    unittest.main()
