"""Offline safety regression: cleanup is not runnable, even with credentials."""
import pathlib
import unittest
from unittest.mock import patch
from deploy import phase0_backed_up_cleanup as cleanup


class QuarantineTests(unittest.TestCase):
    def test_apply_cannot_open_client_or_delete(self):
        with patch.object(cleanup, "client", side_effect=AssertionError("client called")):
            self.assertEqual(cleanup.apply(), 4)

    def test_workflow_has_no_push_or_destructive_job(self):
        workflow = pathlib.Path(".github/workflows/phase0-backed-up-cleanup.yml").read_text()
        self.assertNotIn("push:", workflow)
        self.assertNotIn("delete-backed-up-records:", workflow)
        self.assertNotIn("phase0_backed_up_cleanup apply", workflow)
        self.assertNotIn("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", workflow)
        self.assertIn("if: ${{ false }}", workflow)


if __name__ == "__main__":
    unittest.main()
