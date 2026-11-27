"""Paper execution engine: TP/SL/trail exits, trade cap, day max-loss, kill, EOD.
Synthetic quotes only; fees via the real option_fees model."""
import datetime as dt
import unittest

from india_trader.paper_sim import option_fees
from india_trader.strategies.common import CLOSE, LONG, OPEN, SignalEvent
from india_trader.strategies.paper_exec import OptionQuote, PaperExecutionEngine, RiskParams

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def T(h, m):
    return dt.datetime(2026, 11, 30, h, m, tzinfo=IST)


class Provider:
    def __init__(self, atm, bids):
        self._atm = atm
        self._bids = bids
        self.i = 0

    def atm(self, underlying, side, price, now):
        return self._atm

    def quote(self, symbol, now):
        v = self._bids[min(self.i, len(self._bids) - 1)]
        self.i += 1
        return OptionQuote(symbol, bid=v, ask=v + 1, exchange=self._atm.exchange)


def open_evt(side=LONG, strat="S2_supertrend_sma"):
    return SignalEvent(T(10, 0).isoformat(), OPEN, side, 25000.0, "ENTRY", strat)


RISK = RiskParams(sl_points=30, tp_points=50, max_trades=5, qty=65, exchange="NFO")
KEY = "S2_supertrend_sma|NIFTY"


class ExecEngine(unittest.TestCase):
    def _eng(self, bids):
        atm = OptionQuote("NIFTY2026CE", 99.0, 100.0, "NFO")
        return PaperExecutionEngine(Provider(atm, bids))

    def test_take_profit_nets_gross_minus_fees(self):
        eng = self._eng([150.0])
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 0))
        eng.on_tick(T(10, 5), {KEY: RISK})
        close = [a for a in eng.audit if a["action"] == "CLOSE"][0]
        self.assertEqual(close["exit_type"], "TP")
        fees = option_fees(100.0, 150.0, 65, "NFO", "UPSTOX")["total"]
        self.assertAlmostEqual(close["gross_pnl"], (150 - 100) * 65, places=2)
        self.assertAlmostEqual(close["net_pnl"], (150 - 100) * 65 - fees, places=2)

    def test_stop_loss_exit(self):
        eng = self._eng([70.0])
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 0))
        eng.on_tick(T(10, 5), {KEY: RISK})
        close = [a for a in eng.audit if a["action"] == "CLOSE"][0]
        self.assertEqual(close["exit_type"], "SL")
        self.assertLess(close["net_pnl"], 0)

    def test_trailing_stop(self):
        risk = RiskParams(30, 50, 5, 65, "NFO", trail_start=20, trail_step=10)
        eng = self._eng([130.0, 118.0])
        eng.on_signal(open_evt(), "NIFTY", risk, T(10, 0))
        eng.on_tick(T(10, 5), {KEY: risk})   # arm trail, sl -> 120
        eng.on_tick(T(10, 10), {KEY: risk})  # 118 <= 120 -> TRAIL exit
        close = [a for a in eng.audit if a["action"] == "CLOSE"][0]
        self.assertEqual(close["exit_type"], "TRAIL")
        self.assertGreater(close["exit_premium"], 100)  # exited in profit

    def test_max_trades_blocks_second_open(self):
        risk = RiskParams(30, 50, 1, 65, "NFO")
        eng = self._eng([150.0, 150.0])
        eng.on_signal(open_evt(), "NIFTY", risk, T(10, 0))
        eng.on_tick(T(10, 5), {KEY: risk})       # TP close (trade 1 done)
        eng.on_signal(open_evt(), "NIFTY", risk, T(10, 10))
        self.assertTrue(any(a["action"] == "OPEN_BLOCKED" and a["reason"] == "MAX_TRADES" for a in eng.audit))

    def test_day_max_loss_stops_strategy(self):
        eng = self._eng([70.0])
        eng.set_day_caps("S2_supertrend_sma", "NIFTY", max_loss=1000)
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 0))
        eng.on_tick(T(10, 5), {KEY: RISK})  # ~ -1950 net -> below -1000
        self.assertTrue(any(a["action"] == "STRATEGY_STOPPED" and a["reason"] == "DAY_MAX_LOSS" for a in eng.audit))
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 10))
        self.assertTrue(any(a["action"] == "OPEN_BLOCKED" and a["reason"] == "DAY_MAX_LOSS" for a in eng.audit))

    def test_global_kill_closes_and_blocks(self):
        eng = self._eng([120.0])
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 0))
        eng.set_kill(True)
        eng.on_tick(T(10, 5), {KEY: RISK})
        self.assertTrue(any(a["action"] == "CLOSE" and a["exit_type"] == "KILL" for a in eng.audit))
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 10))
        self.assertTrue(any(a["action"] == "OPEN_BLOCKED" and a["reason"] == "KILL" for a in eng.audit))

    def test_eod_square_off(self):
        eng = self._eng([120.0])
        eng.on_signal(open_evt(), "NIFTY", RISK, T(10, 0))
        eng.on_tick(T(15, 5), {KEY: RISK})
        self.assertTrue(any(a["action"] == "CLOSE" and a["exit_type"] == "EOD" for a in eng.audit))

    def test_no_open_after_square_off(self):
        eng = self._eng([120.0])
        eng.on_signal(open_evt(), "NIFTY", RISK, T(15, 10))
        self.assertFalse(any(a["action"] == "OPEN" for a in eng.audit))


if __name__ == "__main__":
    unittest.main()
