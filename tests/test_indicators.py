"""Verify the shared indicator library against hand-computed canonical values
to 1e-9 (exceeds the spec's 1e-6), plus structural properties. Dependency-free
(no pandas-ta/TA-Lib at test time)."""
import unittest

from india_trader import indicators as ind


class MovingAverages(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(ind.sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_ema_seeded_with_sma(self):
        out = ind.ema([1, 2, 3, 4, 5], 3)
        self.assertEqual(out[:2], [None, None])
        for got, exp in zip(out[2:], [2.0, 3.0, 4.0]):
            self.assertAlmostEqual(got, exp, places=9)

    def test_rma_wilder(self):
        out = ind.rma([1, 2, 3, 4, 5], 3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0, places=9)
        self.assertAlmostEqual(out[3], 2.0 + (4 - 2) / 3, places=9)          # 2.666666667
        self.assertAlmostEqual(out[4], out[3] + (5 - out[3]) / 3, places=9)  # 3.444444444


class RSIandATR(unittest.TestCase):
    def test_rsi_wilder_small(self):
        out = ind.rsi([10, 11, 10.5, 11.5, 11], 2)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 100 - 100 / 3, places=9)   # 66.666666667
        self.assertAlmostEqual(out[3], 100 - 100 / 7, places=9)   # 85.714285714
        self.assertAlmostEqual(out[4], 100 - 100 / 2.2, places=9)  # 54.545454545

    def test_rsi_all_gains_is_100(self):
        out = ind.rsi(list(range(1, 20)), 14)
        self.assertAlmostEqual(out[14], 100.0, places=9)

    def test_atr_wilder_small(self):
        out = ind.atr(highs=[2, 3, 4], lows=[1, 1, 2], closes=[1.5, 2.5, 3.5], n=2)
        self.assertIsNone(out[0])
        self.assertAlmostEqual(out[1], 1.5, places=9)
        self.assertAlmostEqual(out[2], 1.75, places=9)


class MACD(unittest.TestCase):
    def test_constant_series_is_zero(self):
        line, sig, hist = ind.macd([5.0] * 40)
        self.assertAlmostEqual(line[39], 0.0, places=9)
        self.assertAlmostEqual(sig[39], 0.0, places=9)
        self.assertAlmostEqual(hist[39], 0.0, places=9)

    def test_line_is_fast_minus_slow(self):
        closes = [float(i) + (i % 3) for i in range(60)]
        line, _, _ = ind.macd(closes, 12, 26, 9)
        ef, es = ind.ema(closes, 12), ind.ema(closes, 26)
        for i in range(len(closes)):
            if ef[i] is not None and es[i] is not None:
                self.assertAlmostEqual(line[i], ef[i] - es[i], places=9)


class Supertrend(unittest.TestCase):
    def test_uptrend_is_up_and_line_below_close(self):
        closes = [100 + i for i in range(40)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        d, line = ind.supertrend(highs, lows, closes, period=10, mult=3.0)
        self.assertEqual(d[-1], 1)
        self.assertLess(line[-1], closes[-1])

    def test_downtrend_is_down(self):
        closes = [100 - i for i in range(40)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        d, line = ind.supertrend(highs, lows, closes, period=10, mult=3.0)
        self.assertEqual(d[-1], -1)
        self.assertGreater(line[-1], closes[-1])


class UTBot(unittest.TestCase):
    def test_dip_then_rise_triggers_buy_and_trail_below(self):
        # UT Bot "buy" needs a cross UP through the trail, so go down then up.
        closes = [120 - i for i in range(20)] + [100 + i * 2 for i in range(20)]
        trail, buy, sell = ind.ut_bot(closes, a=1.0, c=10)
        self.assertTrue(any(buy[20:]))
        self.assertLessEqual(trail[-1], closes[-1])

    def test_reversal_down_triggers_sell(self):
        closes = [100 + i for i in range(20)] + [120 - i * 2 for i in range(20)]
        _, _, sell = ind.ut_bot(closes, a=1.0, c=10)
        self.assertTrue(any(sell[20:]))


if __name__ == "__main__":
    unittest.main()
