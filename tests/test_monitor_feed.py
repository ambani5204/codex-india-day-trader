"""Monitor feed: journals -> monitor JSON. Tolerant and faithful (no invention)."""
import json
import tempfile
import unittest
from pathlib import Path

from deploy import monitor_feed


class Feed(unittest.TestCase):
    def _journal(self, rows):
        d = Path(tempfile.mkdtemp())
        with (d / "2026-11-30_NIFTY_x.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return str(d)

    def test_empty_dir_no_session(self):
        data = monitor_feed.build(tempfile.mkdtemp(), "2026-11-30")
        self.assertEqual(data["status"], "NO_SESSION")
        self.assertEqual(data["day"]["trades"], 0)
        self.assertEqual(data["day"]["win_rate"], "—")

    def test_closed_trades_aggregate(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "s", "market": "NIFTY", "capital": 15000, "mode": "p"},
            {"event": "INDEX_SIGNAL", "market": "NIFTY", "time": "2026-11-30T09:20:00+05:30",
             "direction": "CE", "signal_close": 25856.4},
            {"event": "OPTION_PAPER_CLOSED", "market": "NIFTY", "strategy": "EMA9_EMA15",
             "symbol": "NIFTYCE", "time": "2026-11-30T09:35:00+05:30",
             "entry_price": 100, "exit_price": 151, "net_pnl_inr": 3185.0, "reason": "TARGET_3R"},
            {"event": "OPTION_PAPER_CLOSED", "market": "NIFTY", "strategy": "EMA9_EMA15",
             "symbol": "NIFTYPE", "time": "2026-11-30T10:35:00+05:30",
             "entry_price": 88, "exit_price": 72, "net_pnl_inr": -1072.0, "reason": "STOP"},
            {"event": "SESSION_SUMMARY", "session": "s", "market": "NIFTY", "status": "COMPLETE", "summary": {}},
        ])
        data = monitor_feed.build(d, "2026-11-30")
        self.assertEqual(data["status"], "COMPLETE")
        self.assertEqual(data["day"]["trades"], 2)
        self.assertAlmostEqual(data["day"]["net_pnl"], 2113.0)
        self.assertEqual(data["day"]["win_rate"], "50%")
        self.assertEqual(len(data["signals"]), 1)
        self.assertEqual(data["strategies"][0]["name"], "EMA9_EMA15")
        self.assertAlmostEqual(data["strategies"][0]["pnl"], 2113.0)

    def test_suite_audit_close(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "suite", "market": "BOTH", "capital": 15000, "mode": "p"},
            {"event": "SUITE_AUDIT", "action": "CLOSE", "strategy": "S4_buffer_breakout",
             "symbol": "NIFTYCE", "ts": "2026-11-30T11:00:00", "net_pnl": 500.0, "exit_type": "TP"},
        ])
        data = monitor_feed.build(d, "2026-11-30")
        self.assertEqual(data["day"]["trades"], 1)
        self.assertAlmostEqual(data["day"]["net_pnl"], 500.0)
        self.assertEqual(data["strategies"][0]["name"], "S4_buffer_breakout")

    def test_malformed_lines_tolerated(self):
        d = self._journal([{"event": "SESSION_START", "session": "s", "market": "N", "capital": 1, "mode": "p"}])
        with (Path(d) / "junk.jsonl").open("w") as f:
            f.write("not json\n{also bad\n")
        data = monitor_feed.build(d, "2026-11-30")
        self.assertIn(data["status"], ("RUNNING", "COMPLETE"))


if __name__ == "__main__":
    unittest.main()
