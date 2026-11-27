"""Offline test of conservative private-archive/live-ledger comparison."""
import unittest
import urllib.error
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
    def test_negative_history_counter_fails_closed(self):
        self.assertEqual(check_match(row(signals_count=-1), EVENTS, 1),
                         "INVALID_HISTORY_COUNTERS")

    def test_coverage_cannot_exceed_closed_trades(self):
        self.assertEqual(check_match(row(pnl_coverage=2), EVENTS, 1),
                         "INVALID_HISTORY_COUNTERS")

    def test_duplicate_session_summaries_fail_closed(self):
        duplicated = EVENTS + [{"event": "SESSION_SUMMARY"}]
        self.assertEqual(check_match(row(), duplicated, 1),
                         "AMBIGUOUS_SESSION_SUMMARIES")


    def test_duplicate_history_date_market_is_blocked(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY"},
            {"date_ist": "2026-11-19", "market": "NIFTY"},
        ]
        self.assertEqual(reconcile.duplicate_history_keys(rows),
                         {("2026-11-19", "NIFTY")})

    def test_distinct_market_date_keys_are_not_duplicates(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY"},
            {"date_ist": "2026-11-19", "market": "SENSEX"},
            {"date_ist": "2026-11-18", "market": "NIFTY"},
        ]
        self.assertEqual(reconcile.duplicate_history_keys(rows), set())


    def test_duplicate_metadata_counts_without_exposing_ids(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY", "_document_name": "secret-doc-a"},
            {"date_ist": "2026-11-19", "market": "NIFTY", "_document_name": "secret-doc-b"},
            {"date_ist": "2026-11-18", "market": "SENSEX", "_document_name": "other"},
        ]
        self.assertEqual(reconcile.duplicate_history_metadata(rows),
                         {"groups": 1, "rows": 2, "missing_names": 0, "repeated_names": 0})
        self.assertNotIn("secret-doc", str(reconcile.duplicate_history_metadata(rows)))

    def test_duplicate_metadata_detects_missing_and_repeated_identity(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY", "_document_name": "same"},
            {"date_ist": "2026-11-19", "market": "NIFTY", "_document_name": "same"},
            {"date_ist": "2026-11-19", "market": "NIFTY"},
        ]
        self.assertEqual(reconcile.duplicate_history_metadata(rows),
                         {"groups": 1, "rows": 3, "missing_names": 1, "repeated_names": 1})

    def test_distinct_session_ids_do_not_bypass_market_date_ambiguity(self):
        # Session IDs are untrusted until cross-source provenance is established.
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY",
             "session_id": "private-session-a", "_document_name": "private-doc-a"},
            {"date_ist": "2026-11-19", "market": "NIFTY",
             "session_id": "private-session-b", "_document_name": "private-doc-b"},
        ]
        self.assertEqual(reconcile.duplicate_history_keys(rows),
                         {("2026-11-19", "NIFTY")})
        diagnostic = reconcile.duplicate_history_metadata(rows)
        self.assertEqual(diagnostic,
                         {"groups": 1, "rows": 2, "missing_names": 0, "repeated_names": 0})
        self.assertNotIn("private-session", str(diagnostic))
        self.assertNotIn("private-doc", str(diagnostic))

    def test_archive_http404_is_not_silently_treated_as_empty(self):
        error = urllib.error.HTTPError("https://api.github.com/example", 404, "Not Found", {}, None)
        with patch.object(reconcile, "gh_get", side_effect=error):
            with self.assertRaises(reconcile.MissingArchiveDate):
                reconcile.load_archives("synthetic-token", "2026-11-14")


    def test_invalid_archive_dates_fail_before_network(self):
        for invalid in ("2026-02-30", "2026-11-14/../15", "2026-11-14?x=1",
                        "2026-11-14T00:00:00", "2026-1-4"):
            with self.subTest(invalid=invalid):
                with patch.object(reconcile, "gh_get") as get:
                    with self.assertRaises(ValueError):
                        reconcile.load_archives("synthetic-token", invalid)
                    get.assert_not_called()

    def test_archive_403_stays_auth_failure(self):
        error = urllib.error.HTTPError("https://api.github.com/example", 403, "Forbidden", {}, None)
        with patch.object(reconcile, "gh_get", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                reconcile.load_archives("synthetic-token", "2026-11-14")
        self.assertEqual(caught.exception.code, 403)

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

    def test_missing_session_summary_is_not_a_verified_session(self):
        events = [e for e in EVENTS if e["event"] != "SESSION_SUMMARY"]
        self.assertEqual(check_match(row(), events, 1), "MISSING_SESSION_SUMMARY")

    def test_session_summary_does_not_prove_terminal_state(self):
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
