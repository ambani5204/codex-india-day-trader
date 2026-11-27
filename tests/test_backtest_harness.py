"""Backtest harness metrics: net P&L, max drawdown, win rate, profit factor
computed from a known sequence of closed trades."""
import unittest

from india_trader.strategies.backtest import metrics_from_closes


class Metrics(unittest.TestCase):
    def test_known_sequence(self):
        trades = [
            {"net_pnl": 100.0, "gross_pnl": 160.0, "fees": 60.0, "entry_premium": 100, "exit_premium": 150},
            {"net_pnl": -50.0, "gross_pnl": 10.0, "fees": 60.0, "entry_premium": 100, "exit_premium": 100.15},
            {"net_pnl": 200.0, "gross_pnl": 260.0, "fees": 60.0, "entry_premium": 100, "exit_premium": 160},
            {"net_pnl": -80.0, "gross_pnl": -20.0, "fees": 60.0, "entry_premium": 100, "exit_premium": 99.7},
        ]
        m = metrics_from_closes(trades)
        self.assertEqual(m["trades"], 4)
        self.assertEqual(m["wins"], 2)
        self.assertEqual(m["win_rate_pct"], 50.0)
        self.assertEqual(m["net_pnl"], 170.0)        # 100-50+200-80
        # equity path: 100, 50, 250, 170 -> peak 250, trough-after 170 -> max dd 80
        self.assertEqual(m["max_drawdown"], 80.0)
        self.assertEqual(m["profit_factor"], round(300 / 130, 2))  # wins 300 / losses 130

    def test_empty(self):
        m = metrics_from_closes([])
        self.assertEqual(m["trades"], 0)
        self.assertIsNone(m["win_rate_pct"])


if __name__ == "__main__":
    unittest.main()
