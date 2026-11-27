"""Fail-closed missing archive classification without exposing private journal data."""
import io
import urllib.error
import unittest
from unittest.mock import patch

from deploy import phase0_firestore_journal_reconcile as audit


class MissingArchiveClassificationTests(unittest.TestCase):
    def test_date_specific_404_is_not_private_repo_failure(self):
        with patch.object(audit, "gh_get", side_effect=urllib.error.HTTPError(
                "https://api.github.com", 404, "Not Found", {}, None)):
            with self.assertRaises(audit.MissingArchiveDate):
                audit.load_archives("redacted", "2026-11-14")

    def test_date_specific_403_remains_auth_error(self):
        with patch.object(audit, "gh_get", side_effect=urllib.error.HTTPError(
                "https://api.github.com", 403, "Forbidden", {}, None)):
            with self.assertRaises(urllib.error.HTTPError) as error:
                audit.load_archives("redacted", "2026-11-14")
            self.assertEqual(error.exception.code, 403)

    def test_bad_date_rejected_before_network(self):
        with patch.object(audit, "gh_get") as get:
            with self.assertRaises(ValueError):
                audit.load_archives("redacted", "2026-02-30")
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
