"""Deterministic unit tests for dashboard analytics; no network, no real orders."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import firebase_live_publisher as publisher


class DashboardAnalyticsTest(unittest.TestCase):
    def test_closed_trade_metrics_and_drawdown(self):
        with tempfile.TemporaryDirectory() as folder:
            day = "2026-11-13"
            events = [
                {"event": "INDEX_SIGNAL", "timestamp": day + "T12:00:00+05:30", "side": "BUY"},
                {"event": "PAPER_BUY_FILLED", "timestamp": day + "T12:25:43+05:30"},
                {"event": "PAPER_TRADE_CLOSED", "timestamp": day + "T14:03:56+05:30",
                 "buy_time": day + "T12:25:43+05:30", "buy_price": 148.57,
                 "sell_price": 132.08, "quantity": 65, "symbol": "NFO:NIFTY_CE",
                 "net_pnl": -1140.12, "gross_pnl": -1071.85, "fees": {"total": 68.27}},
            ]
            Path(folder, day + "_NIFTY_TEST.jsonl").write_text(
                "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            with patch.object(publisher, "JOURNALS", Path(folder)):
                result = publisher.snapshot("NIFTY", "ARCHIVED_SESSION", "test", day=day)
            self.assertEqual(result["signals_count"], 1)
            self.assertEqual(result["closed_trades"], 1)
            self.assertEqual(result["net_pnl"], -1140.12)
            self.assertEqual(result["gross_pnl"], -1071.85)
            self.assertEqual(result["fees_total"], 68.27)
            self.assertEqual(result["winning_trades"], 0)
            self.assertEqual(result["losing_trades"], 1)
            self.assertEqual(result["max_drawdown"], 1140.12)
            self.assertEqual(result["trade_ledger"][0]["quantity"], 65)

    def test_no_closed_trades_does_not_invent_pnl(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(publisher, "JOURNALS", Path(folder)):
                result = publisher.snapshot("NIFTY", "RUNNING", "test", day="2026-11-13")
            self.assertIsNone(result["net_pnl"])
            self.assertIsNone(result["max_drawdown"])
            self.assertEqual(result["closed_trades"], 0)


if __name__ == "__main__":
    unittest.main()
