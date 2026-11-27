"""Fail-closed exit regression: synthetic fixtures are NOT ledger parity evidence."""
import contextlib
import io
import unittest
from unittest.mock import patch

from deploy import phase0_firestore_journal_reconcile as audit


class FailClosedExitTests(unittest.TestCase):
    def test_counter_only_match_is_nonzero(self):
        row = {"date_ist": "2026-11-24", "market": "NIFTY",
               "data_type": "PAPER_SIMULATION", "signals_count": 0,
               "closed_trades": 0, "pnl_coverage": 0, "net_pnl": None}
        with patch.dict("os.environ", {
            "JOURNAL_REPO_TOKEN": "synthetic", 
            "FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET": "synthetic",
            "FIREBASE_PROJECT_ID": "synthetic"}), \
             patch.object(audit, "gh_get", return_value={
                 "full_name": audit.REPOSITORY, "private": True}), \
             patch.object(audit, "get_history", return_value=[row]), \
             patch.object(audit, "load_archives", return_value={
                 "NIFTY": ([{"event": "SESSION_SUMMARY"}], 1),
                 "SENSEX": ([], 0)}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status = audit.main()
        self.assertEqual(status, 4)
        self.assertIn("PHASE0_RECONCILIATION=INCOMPLETE", output.getvalue())
        self.assertIn("SESSION_TERMINATION_AND_OPTIONS_FILLS_UNVERIFIED", output.getvalue())
        self.assertNotIn("PHASE0_RECONCILIATION=COUNTS_MATCH", output.getvalue())

    def test_missing_credentials_is_nonzero(self):
        with patch.dict("os.environ", {
            "JOURNAL_REPO_TOKEN": "",
            "FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET": "",
            "FIREBASE_PROJECT_ID": ""}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status = audit.main()
        self.assertEqual(status, 2)
        self.assertIn("MISSING_CONFIG", output.getvalue())


if __name__ == "__main__":
    unittest.main()
