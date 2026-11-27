"""S2 — Advance Supertrend (SMA + Supertrend), "Dhan Trend" (strategy-spec-dhansetu-v1).

Always-in-market with reversal, evaluated on CLOSED bars:
- Long  when close > SMA(n) AND Supertrend direction = up.
- Short when close < SMA(n) AND Supertrend direction = down.
- Neutral (price and Supertrend disagree) -> hold the current position.
- Reversal emits CLOSE(current) then OPEN(opposite) on the same bar.
- No new OPEN at/after no_new_entries; square off any position at/after square_off.

Pure function; option pricing and SL/TP are handled by the execution layer.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Sequence

from .. import indicators as ind
from .common import CLOSE, LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S2_supertrend_sma"


def signals(bars: Sequence, sma_n: int = 20, st_period: int = 10, st_mult: float = 3.0,
            square_off_ist: str = "1505", no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    sma = ind.sma(closes, sma_n)
    direction, _ = ind.supertrend(highs, lows, closes, st_period, st_mult)
    square_off = hhmm(square_off_ist)
    no_entry = hhmm(no_new_entries_ist)

    out: List[SignalEvent] = []
    pos = 0  # -1 short, 0 flat, +1 long

    def ev(b, action, side, reason):
        out.append(SignalEvent(b.time.isoformat(), action, side, b.close, reason, NAME))

    for i, b in enumerate(bars):
        t = b.time.astimezone(b.time.tzinfo).time()
        if t >= square_off:
            if pos != 0:
                ev(b, CLOSE, pos, "EOD")
                pos = 0
            continue
        if sma[i] is None or direction[i] is None:
            continue
        long_cond = closes[i] > sma[i] and direction[i] == 1
        short_cond = closes[i] < sma[i] and direction[i] == -1
        can_open = t < no_entry
        if long_cond and pos <= 0:
            if pos == SHORT:
                ev(b, CLOSE, SHORT, "REVERSE")
                pos = 0
            if pos == 0 and can_open:
                ev(b, OPEN, LONG, "ENTRY")
                pos = LONG
        elif short_cond and pos >= 0:
            if pos == LONG:
                ev(b, CLOSE, LONG, "REVERSE")
                pos = 0
            if pos == 0 and can_open:
                ev(b, OPEN, SHORT, "ENTRY")
                pos = SHORT
        # neutral or same-direction: hold
    return out
