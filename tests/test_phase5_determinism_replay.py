"""Phase 5: detector determinism + replay parity (no lookahead).

The two properties that make a closed-candle system trustworthy:
  1. Determinism  - same bars in => byte-identical events out, every run.
  2. Replay parity - the event attributed to a closed bar must NOT change when
     later bars are appended. Computing signals over a growing prefix must agree
     with computing them over the full series for every already-closed bar.
     A failure here means the detector peeked at future bars (lookahead bias).
"""
import datetime as dt
import math
import unittest

from india_trader.core import Bar
from india_trader.strategies import (buffer_breakout, orb, reversal_v1, sma_rsi,
                                     supertrend_sma, utbot_macd)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def wave(n=80, base=25000.0, amp=120.0, period=17):
    """Deterministic oscillating 5-min series spanning one session from 09:15."""
    bars = []
    t = dt.datetime(2026, 11, 30, 9, 15, tzinfo=IST)
    for i in range(n):
        c = base + amp * math.sin(2 * math.pi * i / period) + 8 * ((i % 5) - 2)
        o = base + amp * math.sin(2 * math.pi * (i - 1) / period)
        hi = max(o, c) + 15
        lo = min(o, c) - 15
        bars.append(Bar(t + dt.timedelta(minutes=5 * i), o, hi, lo, c))
    return bars


DETECTORS = [
    ("orb", lambda b: orb.signals(b, buffer_points=1)),
    ("supertrend_sma", lambda b: supertrend_sma.signals(b, sma_n=10, st_period=7)),
    ("utbot_macd", lambda b: utbot_macd.signals(b, confirm_window=3)),
    ("buffer_breakout", lambda b: buffer_breakout.signals(b, ref_block_minutes=15, buffer_pct=0.1)),
    ("sma_rsi", lambda b: sma_rsi.signals(b, sma_n=10, rsi_n=7)),
    ("reversal_v1", lambda b: reversal_v1.signals(b)),
]


def _key(evts):
    return [(e.bar_time, e.action, e.side, round(e.price, 6), e.reason) for e in evts]


class Determinism(unittest.TestCase):
    def test_identical_across_runs(self):
        bars = wave()
        for name, fn in DETECTORS:
            with self.subTest(name):
                self.assertEqual(_key(fn(bars)), _key(fn(list(bars))))

    def test_input_not_mutated(self):
        bars = wave()
        snap = [(b.time, b.open, b.high, b.low, b.close) for b in bars]
        for _, fn in DETECTORS:
            fn(bars)
        self.assertEqual(snap, [(b.time, b.open, b.high, b.low, b.close) for b in bars])


class ReplayParity(unittest.TestCase):
    def test_no_lookahead_prefix_stability(self):
        bars = wave()
        fired = 0
        for name, fn in DETECTORS:
            with self.subTest(name):
                full = fn(bars)
                fired += 1 if full else 0
                full_key = _key(full)
                # Every prefix must reproduce exactly the full-series events whose
                # bar_time lies within that prefix — no later bar may alter them.
                for k in range(5, len(bars) + 1):
                    cutoff = bars[k - 1].time.isoformat()
                    prefix_key = _key(fn(bars[:k]))
                    expected = [e for e in full_key if e[0] <= cutoff]
                    self.assertEqual(prefix_key, expected,
                                     f"{name}: lookahead at prefix k={k}")
        self.assertGreater(fired, 0, "no detector fired on the fixture")


if __name__ == "__main__":
    unittest.main()
