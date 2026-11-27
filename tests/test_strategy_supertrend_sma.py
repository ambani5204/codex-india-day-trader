"""S2 Supertrend+SMA detector on synthetic 5-min candles: entry, reversal, EOD,
no-entry-after cutoff."""
import datetime as dt
import unittest

from india_trader.core import Bar
from india_trader.strategies import supertrend_sma as s2
from india_trader.strategies.common import CLOSE, LONG, OPEN, SHORT

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
START = dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST)


def bars_from_closes(closes):
    out = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        o = prev
        hi = max(o, c) + 0.5
        lo = min(o, c) - 0.5
        out.append(Bar(START + dt.timedelta(minutes=5 * i), o, hi, lo, c))
    return out


class S2(unittest.TestCase):
    def _run(self, closes, **kw):
        return s2.signals(bars_from_closes(closes), sma_n=5, st_period=5, st_mult=2.0, **kw)

    def test_entry_reversal_and_eod(self):
        up = [100 + i for i in range(40)]          # steady uptrend -> long
        down = [139 - 2 * i for i in range(40)]    # sharp downtrend -> reverse short
        # pad to reach 15:05 (bar index 70 = 09:15 + 350 min)
        closes = up + down
        while len(closes) < 71:
            closes.append(closes[-1])
        ev = self._run(closes)
        opens_long = [e for e in ev if e.action == OPEN and e.side == LONG]
        opens_short = [e for e in ev if e.action == OPEN and e.side == SHORT]
        self.assertTrue(opens_long, "expected a long entry in the uptrend")
        self.assertTrue(opens_short, "expected a short entry after reversal")
        self.assertEqual(ev[0].action, OPEN)
        self.assertEqual(ev[0].side, LONG)
        # a REVERSE close precedes the short open
        self.assertTrue(any(e.action == CLOSE and e.reason == "REVERSE" for e in ev))
        # last event squares off at EOD
        self.assertEqual(ev[-1].action, CLOSE)
        self.assertEqual(ev[-1].reason, "EOD")
        # grammar mapping
        self.assertEqual(opens_long[0].grammar(), "buy-O")
        self.assertEqual(opens_short[0].grammar(), "sell-O")

    def test_no_new_entry_after_cutoff_but_eod_still_closes(self):
        # flat until late, then an uptrend starting after 14:45 -> no OPEN, no position
        closes = [100] * 68 + [100 + i for i in range(5)]  # uptrend starts ~14:55
        ev = s2.signals(bars_from_closes(closes), sma_n=5, st_period=5, st_mult=2.0)
        self.assertFalse([e for e in ev if e.action == OPEN], "no entries allowed after 14:45")

    def test_eod_closes_an_open_position(self):
        closes = [100 + i for i in range(40)] + [139] * 31  # long opens, holds to EOD
        ev = s2.signals(bars_from_closes(closes), sma_n=5, st_period=5, st_mult=2.0)
        self.assertEqual(ev[0].action, OPEN)
        self.assertEqual(ev[-1].reason, "EOD")
        self.assertEqual(ev[-1].action, CLOSE)


if __name__ == "__main__":
    unittest.main()
