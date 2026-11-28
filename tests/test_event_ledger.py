"""Event-ledger contract validator (Phase 2)."""
import unittest

from india_trader import event_ledger as el

TS = "2026-11-28T"


def ev(kind, t, **extra):
    d = {"event": kind, "timestamp": TS + t + "+05:30"}
    d.update(extra)
    return d


def valid_ledger():
    return [
        ev("SESSION_START", "09:15:00", session="s", market="NIFTY", capital=50000.0, mode="PAPER"),
        ev("INDEX_SIGNAL", "09:35:00", market="NIFTY", side="BUY", strategy="ORB"),
        ev("RISK_PLAN", "09:35:01", market="NIFTY", risk_budget=500),
        ev("STRATEGY_DECISION", "09:35:02", market="NIFTY", strategy="ORB", trade_structure="LONG_CE"),
        ev("SESSION_SUMMARY", "15:00:00", session="s", market="NIFTY", status="CLOSED_OR_NO_TRADE", summary={}),
    ]


class EventContract(unittest.TestCase):
    def test_valid_ledger_passes(self):
        self.assertEqual(el.validate_ledger(valid_ledger()), [])

    def test_missing_universal_field(self):
        self.assertIn("missing universal field 'timestamp'", el.validate_event({"event": "X"}))

    def test_event_specific_required_field(self):
        errs = el.validate_event(ev("SESSION_START", "09:15:00", session="s", market="NIFTY", mode="PAPER"))
        self.assertTrue(any("capital" in e for e in errs))

    def test_naive_timestamp_rejected(self):
        errs = el.validate_event({"event": "X", "timestamp": "2026-11-28T09:15:00"})
        self.assertTrue(any("timezone-aware" in e for e in errs))

    def test_must_start_with_session_start(self):
        led = valid_ledger()[1:]
        self.assertTrue(any("SESSION_START" in e for e in el.validate_ledger(led)))

    def test_must_end_in_terminal_event(self):
        led = valid_ledger()[:-1]
        self.assertTrue(any("terminal" in e for e in el.validate_ledger(led)))

    def test_backwards_timestamp_detected(self):
        led = valid_ledger()
        led[2]["timestamp"] = TS + "09:00:00+05:30"
        self.assertTrue(any("backwards" in e for e in el.validate_ledger(led)))

    def test_unresolved_and_paused_are_terminal(self):
        for term in ("UNRESOLVED_POSITION", "SESSION_PAUSED"):
            led = valid_ledger()[:-1] + [ev(term, "12:20:00", session="s", market="NIFTY")]
            self.assertEqual(el.validate_ledger(led), [])


if __name__ == "__main__":
    unittest.main()
