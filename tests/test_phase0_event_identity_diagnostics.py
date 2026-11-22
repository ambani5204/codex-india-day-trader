"""Synthetic identity diagnostics; no credentials or external services."""
import unittest
from deploy.phase0_event_identity_diagnostics import identity_diagnostics


def sample(signal="s1", trade="t1", session="run1"):
    return [{"event": "INDEX_SIGNAL", "signal_id": signal},
            {"event": "PAPER_TRADE_CLOSED", "trade_id": trade, "net_pnl": 12.5},
            {"event": "SESSION_SUMMARY", "session_id": session}]


class IdentityDiagnosticsTests(unittest.TestCase):
    def test_equal_aggregates_distinct_ids_fail_closed(self):
        result = identity_diagnostics(sample(), sample("s2", "t2"))
        self.assertIn("EVENT_IDENTITY_MISMATCH", result["reasons"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_repeated_trade_id_is_detected(self):
        events = sample() + [{"event": "PAPER_TRADE_CLOSED",
                              "trade_id": "t1", "net_pnl": 0}]
        result = identity_diagnostics(events)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertIn("DUPLICATE_EVENT_ID", result["reasons"])

    def test_missing_identity_fails_closed(self):
        events = sample()
        del events[0]["signal_id"]
        result = identity_diagnostics(events)
        self.assertIn("MISSING_EVENT_ID", result["reasons"])

    def test_same_trade_id_in_distinct_runs_not_assumed_restart(self):
        first = sample(session="run1")
        second = sample(session="run2")
        result = identity_diagnostics(first, second)
        self.assertIn("EVENT_IDENTITY_MISMATCH", result["reasons"])
        self.assertIn("SESSION_LINEAGE_UNVERIFIED", result["reasons"])

    def test_matching_ids_still_do_not_certify_provenance(self):
        result = identity_diagnostics(sample(), sample())
        self.assertEqual(result["reasons"], ["SESSION_LINEAGE_UNVERIFIED"])

    def test_diagnostics_do_not_expose_private_values(self):
        result = identity_diagnostics(sample("secret-signal", "secret-trade"))
        self.assertNotIn("secret-", repr(result))

    def test_invalid_event_shape_fails_closed(self):
        result = identity_diagnostics(sample() + [None])
        self.assertIn("INVALID_EVENT_SHAPE", result["reasons"])


if __name__ == "__main__":
    unittest.main()
