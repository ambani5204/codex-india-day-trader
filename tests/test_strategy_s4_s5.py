"""S4 Buffer Breakout and S5 SMA+RSI detectors on synthetic candles."""
import datetime as dt
import unittest

from india_trader.core import Bar
from india_trader.strategies import buffer_breakout as s4
from india_trader.strategies import sma_rsi as s5
from india_trader.strategies.common import LONG, OPEN, SHORT

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def bar(h, m, o, hi, lo, c):
    return Bar(dt.datetime(2026, 11, 30, h, m, tzinfo=IST), o, hi, lo, c)


class S4Buffer(unittest.TestCase):
    def test_breakout_above_previous_block_high(self):
        # block 0 = 09:15-09:30 (15-min), range ~100-101. Block 1 bar breaks above.
        bars = [
            bar(9, 15, 100, 101, 99.5, 100.5),
            bar(9, 20, 100.5, 101, 100, 100.8),
            bar(9, 25, 100.8, 101, 100.5, 101.0),   # block0 high = 101
            bar(9, 30, 101, 103, 101, 102.5),        # block1: 102.5 > 101 + buffer -> LONG
        ]
        ev = s4.signals(bars, ref_block_minutes=15, buffer_pct=0.1)
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0].action, ev[0].side), (OPEN, LONG))
        self.assertEqual(ev[0].grammar(), "buy-O")

    def test_breakdown_below_previous_block_low_short(self):
        bars = [
            bar(9, 15, 100, 100.5, 99, 99.5),
            bar(9, 20, 99.5, 100, 99, 99.2),
            bar(9, 25, 99.2, 99.5, 98.8, 99.0),      # block0 low = 98.8
            bar(9, 30, 99, 99, 97, 97.5),            # 97.5 < 98.8 - buffer -> SHORT
        ]
        ev = s4.signals(bars, ref_block_minutes=15, buffer_pct=0.1)
        self.assertEqual([(e.action, e.side) for e in ev], [(OPEN, SHORT)])

    def test_one_entry_per_side_per_block(self):
        bars = [bar(9, 15, 100, 101, 99.5, 100.5), bar(9, 20, 100, 101, 100, 100.8),
                bar(9, 25, 100, 101, 100, 101.0)]
        bars += [bar(9, 30, 101, 104, 101, 103), bar(9, 35, 103, 104, 102, 103.5)]  # both in block1
        ev = s4.signals(bars, ref_block_minutes=15, buffer_pct=0.1)
        self.assertEqual(len([e for e in ev if e.side == LONG]), 1)


class S5SmaRsi(unittest.TestCase):
    def _bars(self, closes):
        out = []
        for i, c in enumerate(closes):
            prev = closes[i - 1] if i else c
            out.append(Bar(dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST) + dt.timedelta(minutes=15 * i),
                           prev, max(prev, c) + 0.5, min(prev, c) - 0.5, c))
        return out

    def test_long_entry_edge_triggered_once(self):
        # short periods + few bars so entries land before the 14:45 cutoff
        closes = [100] * 8 + [100 + i * 3 for i in range(1, 8)]
        ev = s5.signals(self._bars(closes), sma_n=5, rsi_n=5, rsi_long=55, rsi_short=45)
        longs = [e for e in ev if e.side == LONG]
        self.assertTrue(longs)
        self.assertEqual(longs[0].action, OPEN)

    def test_short_entry(self):
        closes = [100] * 8 + [100 - i * 3 for i in range(1, 8)]
        ev = s5.signals(self._bars(closes), sma_n=5, rsi_n=5)
        self.assertTrue([e for e in ev if e.side == SHORT])


if __name__ == "__main__":
    unittest.main()
