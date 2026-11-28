"""Phase 11 S11.4: weekly reconciliation report."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from deploy import weekly_report
from india_trader import performance_targets as pt


class Weekly(unittest.TestCase):
    def _journal(self, rows_by_date):
        d = Path(tempfile.mkdtemp())
        for date_str, rows in rows_by_date.items():
            with (d / f"{date_str}_x.jsonl").open("w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        return str(d)

    def test_empty_week_no_data(self):
        r = weekly_report.generate(tempfile.mkdtemp(), dt.date(2026, 12, 4))
        self.assertEqual(r["week"]["sessions"], 0)
        self.assertEqual(r["week"]["verdict"], pt.NO_DATA)
        line = weekly_report.one_line(r)
        self.assertIn("no sessions found", line)

    def test_green_week(self):
        trade = lambda p: {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15",
                           "symbol": "X", "entry_price": 100, "exit_price": 100+p/10,
                           "net_pnl_inr": p}
        rows = {"2026-12-01": [trade(200), trade(150)],
                "2026-12-02": [trade(100)],
                "2026-12-03": [trade(50)]}
        r = weekly_report.generate(self._journal(rows), dt.date(2026, 12, 4))
        self.assertAlmostEqual(r["week"]["net_pnl"], 500.0)
        self.assertEqual(r["week"]["verdict"], pt.GREEN)
        self.assertAlmostEqual(r["per_strategy"]["EMA_9_15"], 500.0)

    def test_stop_week(self):
        rows = {"2026-12-01": [{"event": "OPTION_PAPER_CLOSED", "strategy": "x",
                                "symbol": "y", "entry_price": 100, "exit_price": 0,
                                "net_pnl_inr": -3000}]}
        r = weekly_report.generate(self._journal(rows), dt.date(2026, 12, 4))
        self.assertEqual(r["week"]["verdict"], pt.STOP_HIT)

    def test_mondays_to_friday(self):
        dates = weekly_report._week_dates(dt.date(2026, 12, 4))  # Friday
        self.assertEqual([d.isoformat() for d in dates],
                         ["2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"])


if __name__ == "__main__":
    unittest.main()
