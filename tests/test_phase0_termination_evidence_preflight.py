import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from deploy.phase0_termination_evidence_preflight import assess_termination

IST = ZoneInfo("Asia/Kolkata")


def fixture(**kwargs):
    d = {"session_id": "synthetic-s1", "attempt_id": "synthetic-a1",
         "data_type": "PAPER_SIMULATION", "trading_date_ist": "2026-11-23", "workflow_conclusion": "success",
         "worker_exit_reason": "SCHEDULED_MARKET_CLOSE",
         "worker_started_at": dt.datetime(2026, 11, 23, 9, 15, tzinfo=IST),
         "worker_ended_at": dt.datetime(2026, 11, 23, 15, 30, tzinfo=IST),
         "journal_reconciled": True, "calendar_verified": True}
    d.update(kwargs)
    return d


class TerminationEvidencePreflightTests(unittest.TestCase):
    def test_complete_is_only_eligible_for_further_acceptance(self):
        self.assertEqual(assess_termination(fixture()), "ELIGIBLE_FOR_INDEPENDENT_ACCEPTANCE")

    def test_missing_or_mismatched_trading_date_blocks(self):
        self.assertEqual(assess_termination(fixture(trading_date_ist=None)),
                         "BLOCKED_TRADING_DATE_LINEAGE")
        self.assertEqual(assess_termination(fixture(trading_date_ist="2026-11-24")),
                         "BLOCKED_TRADING_DATE_LINEAGE")

    def test_ci_success_does_not_prove_worker_exit(self):
        self.assertEqual(assess_termination(fixture(worker_exit_reason=None)),
                         "BLOCKED_CI_SUCCESS_NOT_TERMINATION")

    def test_early_success_requires_lineage(self):
        self.assertEqual(assess_termination(fixture(worker_ended_at=dt.datetime(
            2026, 11, 23, 15, 10, tzinfo=IST))), "BLOCKED_EARLY_EXIT_REQUIRES_LINEAGE")

    def test_restart_attempt_is_not_full_session(self):
        self.assertEqual(assess_termination(fixture(worker_exit_reason="RESTARTED")),
                         "BLOCKED_EXIT_REASON_REQUIRES_REVIEW")

    def test_missing_identity_and_type(self):
        self.assertEqual(assess_termination(fixture(session_id=None)),
                         "BLOCKED_MISSING_SESSION_IDENTITY")
        self.assertEqual(assess_termination(fixture(data_type="PROXY_RESEARCH")),
                         "BLOCKED_UNVERIFIED_DATA_TYPE")

    def test_no_unverified_journal_or_calendar(self):
        self.assertEqual(assess_termination(fixture(journal_reconciled=False)),
                         "BLOCKED_JOURNAL_RECONCILIATION")
        self.assertEqual(assess_termination(fixture(calendar_verified=False)),
                         "BLOCKED_CALENDAR_UNVERIFIED")

    def test_missing_and_naive_worker_timestamps(self):
        self.assertEqual(assess_termination(fixture(worker_ended_at=None)),
                         "BLOCKED_MISSING_WORKER_TIMESTAMPS")
        self.assertEqual(assess_termination(fixture(worker_ended_at=dt.datetime(
            2026, 11, 23, 15, 30))), "BLOCKED_INVALID_WORKER_TIMESTAMPS")


if __name__ == "__main__":
    unittest.main()
