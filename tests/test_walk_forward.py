"""Phase 8: walk-forward OOS qualification with frozen thresholds."""
import unittest

from india_trader.strategies import walk_forward as wf
from india_trader.strategies.backtest import metrics_from_closes


def trade(net, entry=100, exit=None):
    exit = entry + net / 10 if exit is None else exit
    return {"net_pnl": net, "gross_pnl": net, "fees": 0.0,
            "entry_premium": entry, "exit_premium": exit}


class WalkForward(unittest.TestCase):
    def test_rolling_windows(self):
        w = list(wf.rolling_windows(10, train=4, test=2, step=2))
        self.assertEqual(len(w), 3)  # [0-4|4-6],[2-6|6-8],[4-8|8-10]
        self.assertEqual(list(w[0][1]), [4, 5])

    def test_frozen_thresholds_not_mutable(self):
        with self.assertRaises(Exception):
            wf.FROZEN.min_profit_factor = 0.1  # frozen dataclass

    def test_winning_strategy_qualifies(self):
        # every OOS window: 4 trades, 75% win, PF high, small drawdown, net>0
        sessions = [[trade(300), trade(300), trade(300), trade(-100)] for _ in range(12)]
        r = wf.evaluate(sessions, metrics_from_closes, train=4, test=2)
        self.assertTrue(r["qualified"])
        self.assertEqual(r["passed_windows"], r["windows"])

    def test_losing_strategy_rejected(self):
        sessions = [[trade(-300), trade(-300), trade(100), trade(100)] for _ in range(12)]
        r = wf.evaluate(sessions, metrics_from_closes, train=4, test=2)
        self.assertFalse(r["qualified"])

    def test_high_winrate_but_bad_pf_rejected(self):
        # 3 tiny wins + 1 huge loss: win rate 75% but net negative, PF < 1
        sessions = [[trade(20), trade(20), trade(20), trade(-500)] for _ in range(12)]
        r = wf.evaluate(sessions, metrics_from_closes, train=4, test=2)
        self.assertFalse(r["qualified"])  # win rate alone cannot qualify

    def test_too_few_windows_not_qualified(self):
        sessions = [[trade(300), trade(300), trade(300)] for _ in range(5)]
        r = wf.evaluate(sessions, metrics_from_closes, train=4, test=1)
        self.assertLess(r["windows"], wf.FROZEN.min_oos_windows)
        self.assertFalse(r["qualified"])


if __name__ == "__main__":
    unittest.main()
