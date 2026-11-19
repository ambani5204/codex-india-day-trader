"""Deterministic checks for the research-only mean-reversion evaluator."""
import datetime as dt
import unittest
from india_trader.core import Bar, IST
from deploy.mean_reversion_365d import evaluate_day, summarize

class MeanReversionResearchTests(unittest.TestCase):
    def test_no_future_bar_is_used_without_history(self):
        day=dt.date(2026,11,18)
        bars=[Bar(dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=5*i),
                  100,101,99,100) for i in range(28)]
        self.assertIsNone(evaluate_day(bars,2.,.0025,2.,10.))

    def test_net_r_includes_cost_and_drawdown(self):
        trades=[{"net_r":2.},{"net_r":-1.},{"net_r":-1.}]
        result=summarize(trades)
        self.assertEqual(result["trades"],3)
        self.assertEqual(result["wins"],1)
        self.assertEqual(result["win_rate_pct"],33.33)
        self.assertEqual(result["net_r"],0.)
        self.assertEqual(result["max_drawdown_r"],2.)

    def test_empty_results_are_not_called_profitable(self):
        result=summarize([])
        self.assertIsNone(result["win_rate_pct"])
        self.assertIsNone(result["profit_factor"])

    def test_cost_gate_prevents_fictional_small_stop_profit(self):
        # High round-trip costs must not manufacture an edge from tiny candle stops.
        day=dt.date(2026,11,18)
        bars=[]
        for i in range(80):
            t=dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=i)
            price=100.0 if i<44 else 99.9
            bars.append(Bar(t,price,price+.01,price-.01,price))
        self.assertIsNone(evaluate_day(bars,1.5,.005,2.,100.))

    def test_summary_negative_result_is_not_profitable(self):
        result=summarize([{"net_r":-1.2},{"net_r":-.8}])
        self.assertLess(result["net_r"],0)
        self.assertEqual(result["profit_factor"],0.)
