"""Synthetic regression tests for CE/PE actionable-signal accounting.

No broker requests, live trades, Firestore mutations or real contract prices.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import firebase_live_publisher as publisher
from deploy.phase0_firestore_journal_reconcile import check_match


DAY = "2026-11-23"
T = DAY + "T10:15:00+05:30"


def long_contract():
    return {
        "symbol": "NFO:NIFTY_25000_2026-11-26_CE",
        "option_type": "CE",
        "expiry": "2026-11-26",
        "risk_plan": {"quantity": 65, "stop_bid": 90.0, "target_bid": 115.0},
    }


def journal_snapshot(events):
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / (DAY + "_NIFTY_ADVANCED_fixture.jsonl")
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        with patch.object(publisher, "JOURNALS", Path(root)):
            return publisher.snapshot("NIFTY", "RUNNING", "synthetic", day=DAY)


class ActionableSignalContractTests(unittest.TestCase):
    def setUp(self):
        self.index = {"event": "INDEX_SIGNAL", "session": "s1",
                      "timestamp": T, "strategy": "MEAN_REVERSION"}
        self.selection = {"event": "OPTION_SELECTION", "session": "s1",
                          "timestamp": T, "contract": long_contract()}
        self.intent = {"event": "ENTRY_SIGNAL", "session": "s1",
                       "timestamp": T, "symbol": long_contract()["symbol"],
                       "reason": "MEAN_REVERSION"}

    def test_raw_index_signal_is_candidate_only(self):
        result = journal_snapshot([self.index])
        self.assertEqual(result["index_candidates_count"], 1)
        self.assertEqual(result["signals_count"], 0)
        self.assertEqual(result["entry_event_count"], 0)
        self.assertEqual(result["events"], [])
        self.assertIsNone(result["net_pnl"])

    def test_validated_long_option_intent_is_visible_before_fill(self):
        result = journal_snapshot([self.index, self.selection, self.intent])
        self.assertEqual(result["index_candidates_count"], 1)
        self.assertEqual(result["signals_count"], 1)
        self.assertEqual(result["entry_event_count"], 0)
        self.assertEqual(result["closed_trades"], 0)
        self.assertIsNone(result["net_pnl"])
        self.assertEqual(result["events"][0]["type"], "ENTRY_SIGNAL")

    def test_missing_contract_selection_blocks_signal(self):
        self.assertEqual(journal_snapshot([self.index, self.intent])["signals_count"], 0)

    def test_invalid_risk_or_option_type_fails_closed(self):
        for update in ({"option_type": "INDEX"}, {"risk_plan": {}},
                       {"risk_plan": {"quantity": 0, "stop_bid": 90, "target_bid": 115}},
                       {"expiry": None}):
            with self.subTest(update=update):
                selection = dict(self.selection, contract={**long_contract(), **update})
                self.assertEqual(journal_snapshot([self.index, selection, self.intent])["signals_count"], 0)

    def test_duplicate_long_intent_same_identity_is_counted_once(self):
        result = journal_snapshot([self.index, self.selection, self.intent, dict(self.intent)])
        self.assertEqual(result["signals_count"], 1)

    def test_selection_after_intent_does_not_qualify(self):
        selection = dict(self.selection, timestamp=DAY + "T10:17:00+05:30")
        self.assertEqual(journal_snapshot([self.index, selection, self.intent])["signals_count"], 0)

    def test_risk_sized_hedged_credit_paper_open_is_actionable(self):
        credit = {
            "event": "PAPER_SPREAD_OPEN", "session": "s1", "timestamp": T,
            "contract": {"option_type": "PE", "expiry": "2026-11-26",
                         "short_key": "NFO|SHORT", "long_key": "NFO|HEDGE",
                         "quantity": 65, "estimated_max_expiry_loss_after_fees": 500},
        }
        result = journal_snapshot([self.index, credit, dict(credit)])
        self.assertEqual(result["index_candidates_count"], 1)
        self.assertEqual(result["signals_count"], 1)
        self.assertEqual(result["entry_event_count"], 2)  # Raw duplicate fill remains an integrity incident.

    def test_naked_or_missing_hedge_credit_not_qualified(self):
        credit = {
            "event": "PAPER_SPREAD_OPEN", "session": "s1", "timestamp": T,
            "contract": {"option_type": "PE", "expiry": "2026-11-26",
                         "short_key": "SAME", "long_key": "SAME", "quantity": 65,
                         "estimated_max_expiry_loss_after_fees": 500},
        }
        self.assertEqual(journal_snapshot([credit])["signals_count"], 0)

    def test_reconciler_compares_index_candidates_not_option_intents(self):
        history = {"data_type": "PAPER_SIMULATION", "signal_contract_version": 2,
                   "signals_count": 0, "index_candidates_count": 1,
                   "closed_trades": 0, "pnl_coverage": 0, "net_pnl": None}
        events = [self.index, {"event": "SESSION_SUMMARY", "session": "s1", "timestamp": T}]
        self.assertEqual(check_match(history, events, 1),
                         "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED")
        del history["index_candidates_count"]
        self.assertEqual(check_match(history, events, 1), "MISSING_COUNTERS")


if __name__ == "__main__":
    unittest.main()
