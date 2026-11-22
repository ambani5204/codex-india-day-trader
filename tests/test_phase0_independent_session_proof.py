"""Synthetic-only negative tests for CHG-20261122-A2-1902."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from deploy.phase0_independent_session_proof import assess_independent_proof

IST = ZoneInfo("Asia/Kolkata")


def fixture():
    return {
        "data_type": "PAPER_SIMULATION", "market": "NIFTY",
        "session_id": "synthetic-session", "attempt_id": "synthetic-attempt",
        "worker_started_at": dt.datetime(2026, 11, 16, 9, 15, tzinfo=IST),
        "worker_ended_at": dt.datetime(2026, 11, 16, 15, 30, tzinfo=IST),
        "trading_date_ist": "2026-11-16", "calendar_exchange": "NSE",
        "calendar_version": "synthetic-v1", "calendar_source_id": "synthetic-source",
        "exchange_session_confirmed": True, "continuous_coverage_verified": True,
        "coverage_evidence_id": "synthetic-coverage", "lease_id": "synthetic-lease",
        "terminal_events": [{"session_id": "synthetic-session", "attempt_id": "synthetic-attempt",
                             "market": "NIFTY", "lease_id": "synthetic-lease",
                             "reason": "SCHEDULED_MARKET_CLOSE"}],
        "journal_reconciled": True,
    }


class IndependentSessionProofTests(unittest.TestCase):
    def test_synthetic_complete_record_only_eligible_for_review(self):
        self.assertEqual(assess_independent_proof(fixture()), "ELIGIBLE_FOR_INDEPENDENT_REVIEW")

    def test_saturday_rejected_despite_claimed_calendar(self):
        x = fixture()
        x["worker_started_at"] = dt.datetime(2026, 11, 14, 9, 15, tzinfo=IST)
        x["worker_ended_at"] = dt.datetime(2026, 11, 14, 15, 30, tzinfo=IST)
        x["trading_date_ist"] = "2026-11-14"
        self.assertEqual(assess_independent_proof(x), "BLOCKED_WEEKEND")

    def test_missing_calendar_provenance(self):
        x = fixture()
        x["calendar_source_id"] = ""
        self.assertEqual(assess_independent_proof(x), "BLOCKED_CALENDAR_PROVENANCE")

    def test_short_worker_window(self):
        x = fixture()
        x["worker_started_at"] = dt.datetime(2026, 11, 16, 15, 29, tzinfo=IST)
        self.assertEqual(assess_independent_proof(x), "BLOCKED_INCOMPLETE_WORKER_WINDOW")

    def test_missing_coverage(self):
        x = fixture()
        x["coverage_evidence_id"] = None
        self.assertEqual(assess_independent_proof(x), "BLOCKED_COVERAGE_LINEAGE")

    def test_cross_market_terminal(self):
        x = fixture()
        x["terminal_events"][0]["market"] = "SENSEX"
        self.assertEqual(assess_independent_proof(x), "BLOCKED_TERMINAL_IDENTITY")

    def test_cross_attempt_terminal(self):
        x = fixture()
        x["terminal_events"][0]["attempt_id"] = "other"
        self.assertEqual(assess_independent_proof(x), "BLOCKED_TERMINAL_IDENTITY")

    def test_missing_terminal(self):
        x = fixture()
        x["terminal_events"] = []
        self.assertEqual(assess_independent_proof(x), "BLOCKED_TERMINAL_EVENT_CARDINALITY")

    def test_duplicate_terminal(self):
        x = fixture()
        x["terminal_events"].append(dict(x["terminal_events"][0]))
        self.assertEqual(assess_independent_proof(x), "BLOCKED_TERMINAL_EVENT_CARDINALITY")

    def test_wrong_lease(self):
        x = fixture()
        x["terminal_events"][0]["lease_id"] = "other"
        self.assertEqual(assess_independent_proof(x), "BLOCKED_TERMINAL_LEASE")

    def test_unconfirmed_exchange_session(self):
        x = fixture()
        x["exchange_session_confirmed"] = False
        self.assertEqual(assess_independent_proof(x), "BLOCKED_EXCHANGE_SESSION_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
