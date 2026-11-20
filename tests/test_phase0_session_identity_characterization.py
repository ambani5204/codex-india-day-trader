"""CHG-20261120-0040: read-only characterization of Phase 0 reconciliation gaps.

These tests document current behavior, NOT acceptance of session-level reconciliation.
No network, credentials, trade data, or Firestore mutations.
"""
import unittest

from deploy.phase0_firestore_journal_reconcile import check_match


class SessionIdentityCharacterization(unittest.TestCase):
    def setUp(self):
        self.history = {
            "data_type": "PAPER_SIMULATION",
            "closed_trades": 0,
            "pnl_coverage": 0,
            "signals_count": 1,
            "net_pnl": None,
            "session_id": "NIFTY-SESSION-A",
        }
        self.events = [
            {"event": "INDEX_SIGNAL", "session_id": "NIFTY-SESSION-B"}
        ]

    def test_different_session_ids_currently_appear_count_matched(self):
        # This is a KNOWN GAP: no session_id comparison in check_match.
        self.assertEqual(
            check_match(self.history, self.events, 1),
            "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED",
        )

    def test_missing_session_ids_currently_appear_count_matched(self):
        # The current implementation does not enforce identity presence.
        self.history.pop("session_id")
        self.events[0].pop("session_id")
        self.assertEqual(
            check_match(self.history, self.events, 1),
            "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED",
        )

    def test_missing_archive_still_fails_closed(self):
        self.assertEqual(check_match(self.history, self.events, 0), "MISSING_ARCHIVE")


if __name__ == "__main__":
    unittest.main()
