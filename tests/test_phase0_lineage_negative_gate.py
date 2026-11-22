"""Synthetic offline regression tests; no Firestore or market access."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from deploy.phase0_lineage_negative_gate import assess_lineage_evidence

IST = ZoneInfo("Asia/Kolkata")


def fixture():
    start = dt.datetime(2026, 11, 16, 9, 15, tzinfo=IST)
    end = start + dt.timedelta(minutes=3)
    identity = dict(session_id="s", attempt_id="a", market="NIFTY", lease_id="l")
    return dict(**identity, coverage_evidence_id="coverage",
                worker_started_at=start, worker_ended_at=end,
                heartbeats=[dict(**identity, timestamp=start + dt.timedelta(minutes=i)) for i in range(4)],
                terminal_events=[dict(**identity, event_id="evt", timestamp=end,
                                      reason="SCHEDULED_MARKET_CLOSE")])


class NegativeLineageTests(unittest.TestCase):
    def test_synthetic_pass_is_not_session_approval(self):
        self.assertEqual(assess_lineage_evidence(fixture()), "ELIGIBLE_FOR_EXTERNAL_CORROBORATION")

    def test_untyped_lease(self):
        x = fixture()
        x["lease_id"] = {"id": "l"}
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_IDENTITY_TYPE")

    def test_untyped_coverage(self):
        x = fixture()
        x["coverage_evidence_id"] = True
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_IDENTITY_TYPE")

    def test_heartbeat_gap(self):
        x = fixture()
        x["heartbeats"] = [x["heartbeats"][0], x["heartbeats"][-1]]
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_HEARTBEAT_GAP")

    def test_heartbeat_cross_market(self):
        x = fixture()
        x["heartbeats"][1]["market"] = "SENSEX"
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_HEARTBEAT_IDENTITY")

    def test_missing_terminal_event_id(self):
        x = fixture()
        del x["terminal_events"][0]["event_id"]
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_TERMINAL_EVENT_ID")

    def test_terminal_before_final_heartbeat(self):
        x = fixture()
        x["terminal_events"][0]["timestamp"] = x["heartbeats"][1]["timestamp"]
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_TERMINAL_TIME_LINK")

    def test_naive_worker_timestamp(self):
        x = fixture()
        x["worker_started_at"] = x["worker_started_at"].replace(tzinfo=None)
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_TIMEZONE")

    def test_naive_heartbeat_timestamp(self):
        x = fixture()
        x["heartbeats"][1]["timestamp"] = x["heartbeats"][1]["timestamp"].replace(tzinfo=None)
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_HEARTBEAT_TIMESTAMP")

    def test_duplicate_terminal(self):
        x = fixture()
        x["terminal_events"].append(dict(x["terminal_events"][0]))
        self.assertEqual(assess_lineage_evidence(x), "BLOCKED_TERMINAL_CARDINALITY")


if __name__ == "__main__":
    unittest.main()
