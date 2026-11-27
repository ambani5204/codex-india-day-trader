"""CHG-20261123-A2-0658: synthetic negative regressions only."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from test_phase0_scheduled_close_clock_gate import fixture
from deploy.phase0_terminal_consensus_gate import assess_terminal_consensus

IST = ZoneInfo("Asia/Kolkata")


class TerminalConsensusTests(unittest.TestCase):
    def test_malformed_input_fails_closed(self):
        for bad in (None, [], "", 0):
            with self.subTest(value=bad):
                self.assertEqual(assess_terminal_consensus(bad), "BLOCKED_MALFORMED")

    def test_missing_or_malformed_terminal_event_fails_closed(self):
        for events, expected in (
            (None, "BLOCKED_TERMINAL_EVENT_CARDINALITY"),
            ([], "BLOCKED_TERMINAL_EVENT_CARDINALITY"),
            ([None], "BLOCKED_TERMINAL_EVENT_TYPE"),
            ([{}], "BLOCKED_TERMINAL_EVENT_ID"),
        ):
            with self.subTest(events=events):
                r = fixture()
                r["terminal_events"] = events
                self.assertEqual(assess_terminal_consensus(r), expected)

    def test_naive_or_missing_terminal_timestamp_fails_closed(self):
        for stamp in (None, dt.datetime(2026, 11, 23, 15, 30)):
            with self.subTest(timestamp=stamp):
                r = fixture()
                r["terminal_events"][0]["timestamp"] = stamp
                self.assertEqual(assess_terminal_consensus(r), "BLOCKED_TERMINAL_TIMESTAMP")

    def test_november_14_saturday_never_accepted(self):
        # This is calendar-negative evidence, NOT producer provenance or a legacy label.
        r = fixture(day=14)
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_WEEKEND")

    def test_spoofed_heartbeat_identity_blocks(self):
        r = fixture()
        r["heartbeats"][1]["attempt_id"] = "different-attempt"
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_HEARTBEAT_IDENTITY")

    def test_terminal_event_identity_mismatch_blocks(self):
        r = fixture()
        r["terminal_events"][0]["lease_id"] = "different-lease"
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_TERMINAL_IDENTITY")

    def test_valid_still_unverified(self):
        self.assertEqual(assess_terminal_consensus(fixture()),
                         "ELIGIBLE_FOR_EXTERNAL_CALENDAR_AND_PROVENANCE_REVIEW")

    def test_conflicting_second_terminal_blocks(self):
        r = fixture()
        r["terminal_events"].append(dict(r["terminal_events"][0], event_id="other",
                                         reason="WORKER_CRASH"))
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_TERMINAL_EVENT_CARDINALITY")

    def test_duplicate_event_id_blocks(self):
        r = fixture()
        r["terminal_events"].append(dict(r["terminal_events"][0]))
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_TERMINAL_EVENT_CARDINALITY")

    def test_terminal_end_mismatch_blocks(self):
        r = fixture()
        r["terminal_events"][0]["timestamp"] += dt.timedelta(seconds=1)
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_TERMINAL_END_MISMATCH")

    def test_cross_date_end_blocks(self):
        r = fixture()
        r["worker_ended_at"] += dt.timedelta(days=1)
        r["terminal_events"][0]["timestamp"] += dt.timedelta(days=1)
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_CROSS_DATE_TERMINAL")

    def test_premature_close_remains_blocked(self):
        r = fixture(close_hour=15, close_minute=29)
        self.assertEqual(assess_terminal_consensus(r), "BLOCKED_PREMATURE_SCHEDULED_CLOSE")


if __name__ == "__main__":
    unittest.main()
