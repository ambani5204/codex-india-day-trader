"""S1 — Opening Range Breakout (strategy-spec-dhansetu-v1 §S1).

Range = high/low of the opening window (default 09:15:00-09:59:59). After the
window, a close beyond range-high+buffer -> long (CE); below range-low-buffer ->
short (PE). One position at a time, max_trades/day, 15:05 square-off. Evaluated
on CLOSED bars (confirmation mode); buffer in points.

Pure function; option pricing and SL/TP handled by the execution layer.
"""
from __future__ import annotations

from typing import List, Sequence

from .common import CLOSE, LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S1_orb"


def signals(bars: Sequence, range_start_ist: str = "0915", range_end_ist: str = "1000",
            buffer_points: float = 0.0, max_trades: int = 3,
            square_off_ist: str = "1505", no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    r_start, r_end = hhmm(range_start_ist), hhmm(range_end_ist)
    square_off, no_entry = hhmm(square_off_ist), hhmm(no_new_entries_ist)

    rng_high = rng_low = None
    for b in bars:
        t = b.time.time()
        if r_start <= t < r_end:
            rng_high = b.high if rng_high is None else max(rng_high, b.high)
            rng_low = b.low if rng_low is None else min(rng_low, b.low)

    out: List[SignalEvent] = []
    pos = 0
    trades = 0

    def ev(b, action, side, reason):
        out.append(SignalEvent(b.time.isoformat(), action, side, b.close, reason, NAME))

    if rng_high is None:
        return out

    for b in bars:
        t = b.time.time()
        if t >= square_off:
            if pos != 0:
                ev(b, CLOSE, pos, "EOD")
                pos = 0
            continue
        if t < r_end:
            continue  # range still forming
        if pos != 0 or trades >= max_trades or t >= no_entry:
            continue
        if b.close > rng_high + buffer_points:
            ev(b, OPEN, LONG, "BREAKOUT_HIGH")
            pos = LONG
            trades += 1
        elif b.close < rng_low - buffer_points:
            ev(b, OPEN, SHORT, "BREAKOUT_LOW")
            pos = SHORT
            trades += 1
    return out
