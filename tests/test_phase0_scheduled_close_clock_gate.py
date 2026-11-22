"""Offline-only scheduled-close regressions; no external I/O."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from deploy.phase0_scheduled_close_clock_gate import assess_scheduled_close

IST = ZoneInfo("Asia/Kolkata")


def fixture(day=16, close_hour=15, close_minute=30):
    start = dt.datetime(2026, 11, day, 9, 15, tzinfo=IST)
    end = start.replace(hour=close_hour, minute=close_minute)
    identity = dict(session_id="s", attempt_id="a", market="NIFTY", lease_id="l")
    beats = []
    cursor = start
    while cursor <= end:
        beats.append(dict(**identity, timestamp=cursor))
        cursor += dt.timedelta(minutes=1)
    return dict(**identity, coverage_evidence_id="coverage",
                worker_started_at=start, worker_ended_at=end, heartbeats=beats,
                terminal_events=[dict(**identity, event_id="evt", timestamp=end,
                                      reason="SCHEDULED_MARKET_CLOSE")])


class ScheduledCloseTests(unittest.TestCase):
    def test_early_0918_is_blocked(self):
        self.assertEqual(assess_scheduled_close(fixture(close_hour=9, close_minute=18)),
                         "BLOCKED_PREMATURE_SCHEDULED_CLOSE")

    def test_1529_is_blocked(self):
        self.assertEqual(assess_scheduled_close(fixture(close_hour=15, close_minute=29)),
                         "BLOCKED_PREMATURE_SCHEDULED_CLOSE")

    def test_1530_remains_unverified(self):
        self.assertEqual(assess_scheduled_close(fixture()),
                         "ELIGIBLE_FOR_EXTERNAL_CALENDAR_AND_PROVENANCE_REVIEW")

    def test_weekend_is_blocked(self):
        self.assertEqual(assess_scheduled_close(fixture(day=14)),
                         "BLOCKED_WEEKEND")

    def test_missing_terminal_identity_still_blocks(self):
        record = fixture()
        del record["terminal_events"][0]["event_id"]
        self.assertEqual(assess_scheduled_close(record), "BLOCKED_TERMINAL_EVENT_ID")

    def test_heartbeat_gap_still_blocks(self):
        record = fixture()
        del record["heartbeats"][3:8]
        self.assertEqual(assess_scheduled_close(record), "BLOCKED_HEARTBEAT_GAP")


if __name__ == "__main__":
    unittest.main()
