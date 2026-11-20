"""Offline test of conservative private-archive/live-ledger comparison."""
import unittest
import urllib.error
from unittest.mock import patch

from deploy.phase0_firestore_journal_reconcile import (
    as_number, summarize_events, check_match, load_archives,
)


def row(**overrides):
    result = {
        "data_type": "PAPER_SIMULATION",
        "closed_trades": 1,
        "pnl_coverage": 1,
        "signals_count": 1,
        "net_pnl": -12.0,
    }
    result.update(overrides)
    return result


EVENTS = [
    {"event": "INDEX_SIGNAL"},
    {"event": "PAPER_TRADE_CLOSED", "net_pnl": -12.0},
    {"event": "SESSION_SUMMARY"},
]


class FirestoreArchiveReconcileTests(unittest.TestCase):
    def test_archive_directory_404_fails_closed_not_empty(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/placeholder", 404, "Not Found", {}, None
        )
        with patch("deploy.phase0_firestore_journal_reconcile.gh_get", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                load_archives("not-a-real-token", "2026-11-19")
        self.assertEqual(raised.exception.code, 404)

    def test_archive_other_http_failure_fails_closed(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/placeholder", 403, "Forbidden", {}, None
        )
        with patch("deploy.phase0_firestore_journal_reconcile.gh_get", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                load_archives("not-a-real-token", "2026-11-19")

    def test_verified_counts_do_not_claim_session_reconciliation(self):
        self.assertEqual(check_match(row(), EVENTS, 1),
                         "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED")

    def test_missing_archive_is_not_zero_trades(self):
        self.assertEqual(check_match(row(closed_trades=0, signals_count=0,
                                         pnl_coverage=0, net_pnl=None), [], 0),
                         "MISSING_ARCHIVE")

    def test_partial_pnl_never_counts_as_fully_verified(self):
        events = [{"event": "PAPER_TRADE_CLOSED", "net_pnl": None}]
        self.assertEqual(check_match(row(closed_trades=1, signals_count=0,
                                         pnl_coverage=0, net_pnl=None), events, 1),
                         "PARTIAL_FINANCIAL_COVERAGE")

    def test_mismatched_amount_fails_closed(self):
        self.assertEqual(check_match(row(net_pnl=-11.0), EVENTS, 1),
                         "PNL_MISMATCH")

    def test_mismatched_event_count_fails_closed(self):
        self.assertEqual(check_match(row(closed_trades=2), EVENTS, 1),
                         "COUNTER_MISMATCH")

    def test_bool_and_non_finite_are_not_numeric_profit(self):
        self.assertIsNone(as_number(True))
        self.assertIsNone(as_number(float("nan")))
        self.assertIsNone(as_number(float("inf")))
        self.assertEqual(summarize_events([
            {"event": "PAPER_TRADE_CLOSED", "net_pnl": True},
            {"event": "PAPER_TRADE_CLOSED", "net_pnl": None},
        ])["coverage"], 0)


if __name__ == "__main__":
    unittest.main()
