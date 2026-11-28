"""S1/S3/S6/S7 detectors: each signal type on crafted synthetic candles."""
import datetime as dt
import unittest

from india_trader.core import Bar
from india_trader.strategies import orb, reversal_v1, rsima_scanner, utbot_macd
from india_trader.strategies.common import CLOSE, LONG, OPEN, SHORT

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def bar(h, m, o, hi, lo, c, day=30):
    return Bar(dt.datetime(2026, 11, day, h, m, tzinfo=IST), o, hi, lo, c)


class ORB(unittest.TestCase):
    def _range(self):
        # 09:15-09:55 range 100-110 (ends 10:00)
        return [bar(9, 15 + 5 * i, 105, 110, 100, 105) for i in range(9)]

    def test_breakout_high_long(self):
        bars = self._range() + [bar(10, 0, 110, 116, 109, 115)]
        s = orb.signals(bars, buffer_points=1)
        self.assertEqual((s[0].action, s[0].side), (OPEN, LONG))
        self.assertEqual(s[0].reason, "BREAKOUT_HIGH")

    def test_breakout_low_short(self):
        bars = self._range() + [bar(10, 0, 100, 101, 90, 95)]
        s = orb.signals(bars, buffer_points=1)
        self.assertEqual((s[0].action, s[0].side), (OPEN, SHORT))

    def test_eod_closes(self):
        bars = self._range() + [bar(10, 0, 110, 116, 109, 115), bar(15, 5, 115, 116, 114, 115)]
        s = orb.signals(bars, buffer_points=1)
        self.assertEqual(s[-1].reason, "EOD")

    def test_max_trades(self):
        bars = self._range()
        for i in range(6):  # alternate breakouts; only one open at a time + cap
            bars.append(bar(10, 5 * (i + 1), 100, 130, 70, 130 if i % 2 == 0 else 70))
        opens = [e for e in orb.signals(bars, buffer_points=1, max_trades=2) if e.action == OPEN]
        self.assertLessEqual(len(opens), 2)


class UTBotMACD(unittest.TestCase):
    def _reversal_series(self):
        # uptrend -> shallow dip (UT buy on recovery) -> recovery with MACD bullish
        seq = [100.0]
        for _ in range(30): seq.append(seq[-1] + 2)
        for _ in range(1): seq.append(seq[-1] - 8)
        for _ in range(10): seq.append(seq[-1] + 5)
        bars, t = [], dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST)
        for c in seq:
            bars.append(Bar(t, c, c + 2, c - 2, c)); t += dt.timedelta(minutes=5)
        return bars

    def test_opens_long_with_window(self):
        # confirm_window (spec §S3 k option): UT buy within last k bars + MACD bullish now
        s = self._reversal_series()
        self.assertTrue(any(e.action == OPEN and e.side == LONG
                            for e in utbot_macd.signals(s, confirm_window=5)))

    def test_strict_mode_is_tighter(self):
        s = self._reversal_series()
        strict = [e for e in utbot_macd.signals(s, confirm_window=0) if e.action == OPEN]
        windowed = [e for e in utbot_macd.signals(s, confirm_window=5) if e.action == OPEN]
        self.assertLessEqual(len(strict), len(windowed))  # AND on the same bar is tighter

    def test_deterministic(self):
        seq = [100 + (i % 7) + i * 0.3 for i in range(60)]
        bars, t = [], dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST)
        for c in seq:
            bars.append(Bar(t, c, c + 1, c - 1, c)); t += dt.timedelta(minutes=5)
        k = lambda evs: [(e.bar_time, e.action, e.side) for e in evs]
        self.assertEqual(k(utbot_macd.signals(bars)), k(utbot_macd.signals(list(bars))))


class RSIMAScanner(unittest.TestCase):
    def test_buy_then_exit(self):
        # downtrend (RSI-MA low) then sustained uptrend (RSI-MA rises above 40) then drop
        closes = [100 - i for i in range(40)] + [60 + 2 * i for i in range(40)] + [140 - 3 * i for i in range(20)]
        base = dt.datetime(2026, 1, 1, 15, 30, tzinfo=IST)
        bars = [Bar(base + dt.timedelta(days=i), c, c + 1, c - 1, c) for i, c in enumerate(closes)]
        s = rsima_scanner.signals(bars)
        acts = [(e.action, e.side, e.reason) for e in s]
        self.assertTrue(any(a == OPEN and side == LONG for a, side, _ in acts))
        self.assertTrue(all(side == LONG for _, side, _ in acts))  # buy-only

    def test_no_shorts_ever(self):
        closes = list(range(50, 10, -1))
        base = dt.datetime(2026, 1, 1, 15, 30, tzinfo=IST)
        bars = [Bar(base + dt.timedelta(days=i), c, c + 1, c - 1, c)
                for i, c in enumerate(closes)]
        self.assertFalse([e for e in rsima_scanner.signals(bars) if e.side == SHORT])


class Reversal(unittest.TestCase):
    def test_support_rejection_long(self):
        # previous day establishes a low level at 100
        prev = [bar(10, 0, 105, 106, 100, 104, day=27)]
        # opening range today 103-108
        rng = [bar(9, 15 + 5 * i, 105, 108, 103, 105) for i in range(9)]
        # a bar that tags 100 (prev-day low) with a long lower wick and closes above
        tag = bar(10, 0, 101, 101.5, 100.02, 101.3)  # body 0.3, lower wick ~1.28 >= 2x body
        s = reversal_v1.signals(prev + rng + [tag], tag_pct=0.001)
        self.assertTrue(any(e.action == OPEN and e.side == LONG for e in s))


if __name__ == "__main__":
    unittest.main()
