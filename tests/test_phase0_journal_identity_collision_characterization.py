"""Phase 0 synthetic characterization: equal aggregates are not event identity proof.

No credentials, network, private records, Firestore writes or orders.
"""
import unittest

from deploy.phase0_firestore_journal_reconcile import check_match, summarize_events


def event_set(signal_id, trade_id, pnl=12.5):
    return [
        {"event": "INDEX_SIGNAL", "signal_id": signal_id, "strategy": "EMA"},
        {"event": "PAPER_TRADE_CLOSED", "trade_id": trade_id, "net_pnl": pnl},
        {"event": "SESSION_SUMMARY", "session_id": "session-A"},
    ]


HISTORY = {
    "data_type": "PAPER_SIMULATION",
    "signals_count": 1,
    "closed_trades": 1,
    "pnl_coverage": 1,
    "net_pnl": 12.5,
}


class IdentityCollisionCharacterization(unittest.TestCase):
    def test_distinct_event_identities_have_identical_aggregates(self):
        a = event_set("signal-1", "trade-1")
        b = event_set("signal-2", "trade-2")
        self.assertNotEqual(a, b)
        self.assertEqual(summarize_events(a), summarize_events(b))
        self.assertEqual(check_match(HISTORY, a, 1),
                         "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED")
        self.assertEqual(check_match(HISTORY, b, 1),
                         "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED")

    def test_repeated_trade_id_is_not_detected_by_aggregate_comparison(self):
        events = [
            {"event": "INDEX_SIGNAL", "signal_id": "signal-1"},
            {"event": "PAPER_TRADE_CLOSED", "trade_id": "same", "net_pnl": 5.0},
            {"event": "PAPER_TRADE_CLOSED", "trade_id": "same", "net_pnl": 7.5},
            {"event": "SESSION_SUMMARY", "session_id": "session-A"},
        ]
        history = dict(HISTORY, closed_trades=2, pnl_coverage=2)
        self.assertEqual(check_match(history, events, 1),
                         "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED")

    def test_missing_net_pnl_is_not_zero(self):
        events = event_set("signal-1", "trade-1")
        del events[1]["net_pnl"]
        history = dict(HISTORY, pnl_coverage=0, net_pnl=None)
        self.assertEqual(check_match(history, events, 1),
                         "PARTIAL_FINANCIAL_COVERAGE")

    def test_no_session_summary_fails_closed(self):
        self.assertEqual(check_match(HISTORY, event_set("s", "t")[:2], 1),
                         "MISSING_SESSION_SUMMARY")


if __name__ == "__main__":
    unittest.main()
