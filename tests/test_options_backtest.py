"""options_backtest wiring: BS provider prices, detectors run through the engine
on synthetic bars (pipeline check only; not a result)."""
import datetime as dt
import unittest

from india_trader.core import Bar
from india_trader.strategies.options_backtest import BSProvider, DETECTORS, RISK
from india_trader.strategies.backtest import metrics_from_closes, run_session
from india_trader.strategies.common import LONG, SignalEvent

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class Wiring(unittest.TestCase):
    def _session(self, n=75, base=25600):
        return [Bar(dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST) + dt.timedelta(minutes=5 * i),
                    base + i, base + i + 5, base + i - 5, base + i + 2) for i in range(n)]

    def test_bs_provider_prices_atm(self):
        p = BSProvider("NIFTY", 0.15, 3.0)
        q = p.atm("NIFTY", LONG, 25600.0, dt.datetime(2026, 11, 30, 10, 0, tzinfo=IST))
        self.assertIsNotNone(q)
        self.assertGreater(q.ask, q.bid)
        self.assertEqual(q.exchange, "NFO")

    def test_detectors_run_through_engine(self):
        bars = self._session()
        for name, detect in DETECTORS.items():
            evs = detect(bars, "NIFTY")
            evs = [SignalEvent(e.bar_time, e.action, e.side, e.price, e.reason, name) for e in evs]
            closed = run_session(evs, bars, BSProvider("NIFTY", 0.15, 3.0), "NIFTY", RISK["NIFTY"])
            m = metrics_from_closes(closed)
            self.assertIn("net_pnl", m)  # pipeline produced metrics without error


if __name__ == "__main__":
    unittest.main()
