import datetime as dt
import unittest
from india_trader.core import Bar, IST
from india_trader.ema9_fib_pivot_research import fibonacci_pivots, signals


class Ema9FibPivotTests(unittest.TestCase):
    def bars(self, day, closes):
        return [Bar(dt.datetime.combine(day, dt.time(9, 15), IST)
                    + dt.timedelta(minutes=5*i),
                    close, close+1, close-1, close)
                for i, close in enumerate(closes)]

    def test_fibonacci_previous_day(self):
        bars = self.bars(dt.date(2026, 11, 12), [100, 110, 105])
        p = fibonacci_pivots(bars)
        self.assertAlmostEqual(p["P"], (111+99+105)/3)
        self.assertAlmostEqual(p["R1"], p["P"] + .382*12)

    def test_rr_validation(self):
        with self.assertRaises(ValueError):
            signals([], [], 1.5)

    def test_morning_cutoff_blocks_afternoon_breakout(self):
        previous = self.bars(dt.date(2026, 11, 12), [100] * 10)
        # P=100; candle at 12:00 breaks above both P and EMA9.
        closes = [100] * 33 + [110]
        today = self.bars(dt.date(2026, 11, 13), closes)
        self.assertEqual(signals(today, previous, 3.0), [])
        baseline = signals(today, previous, 3.0, entry_cutoff=dt.time(14, 45))
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0]["direction"], "BULL")

    def test_no_signal_without_enough_closed_candles(self):
        self.assertEqual(signals(self.bars(dt.date(2026, 11, 13), [100]*9),
                                 self.bars(dt.date(2026, 11, 12), [100]*10)), [])


if __name__ == "__main__":
    unittest.main()
