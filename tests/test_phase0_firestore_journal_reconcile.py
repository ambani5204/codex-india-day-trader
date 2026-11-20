"""Offline test of conservative private-archive/live-ledger comparison."""
import unittest
from unittest.mock import patch
from deploy import phase0_firestore_journal_reconcile as reconcile

from deploy.phase0_firestore_journal_reconcile import (
    as_number, summarize_events, check_match,
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
    def test_repository_metadata_uses_canonical_url_without_trailing_slash(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"full_name":"ambani5204/codex-trading-journals","private":true}'
        captured = []
        def fake_open(request, timeout):
            captured.append(request.full_url)
            return FakeResponse()
        with patch.object(reconcile.urllib.request, "urlopen", side_effect=fake_open):
            result = reconcile.gh_get("synthetic-token", "/")
        self.assertEqual(captured, [reconcile.API])
        self.assertTrue(result["private"])


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
