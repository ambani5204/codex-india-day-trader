"""Phase 11 S11.2: daily goal tracker end-to-end."""
import json
import tempfile
import unittest
from pathlib import Path

from deploy import daily_goal_check
from india_trader import performance_targets as pt


class GoalCheck(unittest.TestCase):
    def _journal(self, rows):
        d = Path(tempfile.mkdtemp())
        with (d / "x.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return str(d)

    def test_empty_dir_no_data(self):
        r = daily_goal_check.check(tempfile.mkdtemp(), "2026-12-01")
        self.assertEqual(r["verdict"], pt.NO_DATA)

    def test_green_day_from_trades(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "s", "market": "N", "capital": 15000, "mode": "p"},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "X",
             "time": "2026-12-01T09:35:00+05:30", "entry_price": 100, "exit_price": 150, "net_pnl_inr": 200},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "Y",
             "time": "2026-12-01T10:35:00+05:30", "entry_price": 80, "exit_price": 110, "net_pnl_inr": 150},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "Z",
             "time": "2026-12-01T11:35:00+05:30", "entry_price": 60, "exit_price": 75, "net_pnl_inr": 75},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "W",
             "time": "2026-12-01T12:35:00+05:30", "entry_price": 60, "exit_price": 68, "net_pnl_inr": 50},
            {"event": "SESSION_SUMMARY", "session": "s", "market": "N", "status": "COMPLETE", "summary": {}},
        ])
        r = daily_goal_check.check(d, "2026-12-01")
        self.assertEqual(r["verdict"], pt.GREEN)
        self.assertEqual(r["cadence"], "ON_TARGET")

    def test_stop_hit_day(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "s", "market": "N", "capital": 15000, "mode": "p"},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "X",
             "time": "2026-12-01T09:35:00+05:30", "entry_price": 100, "exit_price": 70, "net_pnl_inr": -650},
        ])
        r = daily_goal_check.check(d, "2026-12-01")
        self.assertEqual(r["verdict"], pt.STOP_HIT)

    def test_one_line_summary(self):
        r = daily_goal_check.check(tempfile.mkdtemp(), "2026-12-01")
        line = daily_goal_check.one_line(r)
        self.assertIn("no session data yet", line)


if __name__ == "__main__":
    unittest.main()
