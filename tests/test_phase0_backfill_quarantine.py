"""Fail-closed regressions for historical Firestore backfill quarantine.

Intentionally no credentials, private data, network or Firestore changes.
"""
import pathlib
import unittest
from unittest.mock import patch

from deploy import backfill_firestore_from_private_journals as backfill


class BackfillQuarantineTests(unittest.TestCase):
    def test_main_aborts_before_archive_api_or_firestore(self):
        with patch.object(backfill, "call", side_effect=AssertionError("archive network called")):
            with patch.object(backfill, "publish", side_effect=AssertionError("Firestore writer called")):
                self.assertEqual(backfill.main(), 4)

    def test_workflow_cannot_autorun_or_load_secrets(self):
        workflow = pathlib.Path(".github/workflows/backfill-firestore-paper-history.yml").read_text()
        self.assertNotIn("push:", workflow)
        self.assertNotIn("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", workflow)
        self.assertNotIn("JOURNAL_REPO_TOKEN", workflow)
        self.assertNotIn("deploy.backfill_firestore_from_private_journals", workflow)
        self.assertIn("if: ${{ false }}", workflow)

    def test_source_retains_explicit_failclosed_before_network(self):
        source = pathlib.Path("deploy/backfill_firestore_from_private_journals.py").read_text()
        start = source.index("def main():")
        guard = source.index("return 4", start)
        archive_api = source.index("token = os.environ.get", start)
        self.assertLess(guard, archive_api)
        self.assertIn("raise SystemExit(main())", source)


if __name__ == "__main__":
    unittest.main()
