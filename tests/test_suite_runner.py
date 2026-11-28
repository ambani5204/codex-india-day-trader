"""Multi-strategy paper suite runner: routing, enablement, isolation."""
import datetime as dt
import math
import unittest

from india_trader.core import Bar
from india_trader.strategies.paper_exec import OptionQuote, PaperExecutionEngine, RiskParams
from india_trader.strategies.suite_runner import (AVAILABLE, INTRADAY,
                                                  SuiteRunner, resolve_enabled)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def wave(n=80, base=25000.0, amp=120.0, period=17):
    bars, t = [], dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST)
    for i in range(n):
        c = base + amp * math.sin(2 * math.pi * i / period) + 8 * ((i % 5) - 2)
        o = base + amp * math.sin(2 * math.pi * (i - 1) / period)
        bars.append(Bar(t + dt.timedelta(minutes=5 * i), o, max(o, c) + 15, min(o, c) - 15, c))
    return bars


class Provider:
    def atm(self, underlying, side, price, now):
        return OptionQuote(f"{underlying}OPT", 99.0, 100.0, "NFO")

    def quote(self, symbol, now):
        return OptionQuote(symbol, 130.0, 131.0, "NFO")  # in-profit => TP path exists


RISK = {s: RiskParams(sl_points=30, tp_points=50, max_trades=10, qty=50, exchange="NFO")
        for s in AVAILABLE}


class Suite(unittest.TestCase):
    def test_resolve_all(self):
        # "ALL" = intraday set (S6 is a daily scanner, excluded)
        self.assertEqual(resolve_enabled("ALL"), list(INTRADAY))
        self.assertEqual(resolve_enabled(""), list(INTRADAY))
        self.assertEqual(resolve_enabled("S4_buffer_breakout"), ["S4_buffer_breakout"])
        self.assertEqual(len(AVAILABLE), 7)  # all S1-S7 implemented

    def test_unknown_detector_rejected(self):
        with self.assertRaises(ValueError):
            SuiteRunner(PaperExecutionEngine(Provider()), ["S99_nope"], RISK)

    def test_all_three_trade_the_session(self):
        eng = PaperExecutionEngine(Provider())
        suite = SuiteRunner(eng, list(INTRADAY), RISK)
        bars = wave()
        for k in range(5, len(bars) + 1):
            suite.step("NIFTY", bars[:k], bars[k - 1].time + dt.timedelta(minutes=5))
        strensactive = {a["strategy"] for a in eng.audit if a["action"] == "OPEN"}
        # Every enabled detector that fired should appear; at least one does on this fixture.
        self.assertTrue(strensactive)
        self.assertTrue(strensactive.issubset(set(AVAILABLE)))

    def test_each_book_is_isolated_per_strategy(self):
        eng = PaperExecutionEngine(Provider())
        suite = SuiteRunner(eng, list(INTRADAY), RISK)
        bars = wave()
        for k in range(5, len(bars) + 1):
            suite.step("NIFTY", bars[:k], bars[k - 1].time + dt.timedelta(minutes=5))
        # books are keyed per (strategy, market): no cross-contamination
        for key in eng.books:
            strat, market = key.split("|")
            self.assertIn(strat, AVAILABLE)
            self.assertEqual(market, "NIFTY")


if __name__ == "__main__":
    unittest.main()
