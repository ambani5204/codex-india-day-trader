"""S3 — UT Bot + MACD ("Dhan Super" / Vanguard Momentum), spec §S3.

5-min, on CLOSED bars. Long when UT Bot buy-cross AND MACD bullish (line>signal)
on the same bar; short mirror. Opposite signal reverses (CLOSE then OPEN on the
same bar). 15:05 square-off, no new entries after 14:45.

Pure function; option pricing and SL/TP handled by the execution layer.
"""
from __future__ import annotations

from typing import List, Sequence

from .. import indicators as ind
from .common import CLOSE, LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S3_utbot_macd"


def signals(bars: Sequence, ut_key: float = 1.0, ut_atr: int = 10,
            macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
            confirm_window: int = 0,
            square_off_ist: str = "1505", no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    """confirm_window k (spec §S3): a UT buy/sell within the last k closed bars
    still counts when MACD agrees now. k=0 = strict same-bar (spec default)."""
    bars = sorted(bars, key=lambda b: b.time)
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    _, buy, sell = ind.ut_bot(closes, ut_key, ut_atr, highs=highs, lows=lows)
    line, sig, _ = ind.macd(closes, macd_fast, macd_slow, macd_signal)
    square_off, no_entry = hhmm(square_off_ist), hhmm(no_new_entries_ist)

    out: List[SignalEvent] = []
    pos = 0
    last_buy = last_sell = -10**9

    def ev(b, action, side, reason):
        out.append(SignalEvent(b.time.isoformat(), action, side, b.close, reason, NAME))

    for i, b in enumerate(bars):
        if buy[i]:
            last_buy = i
        if sell[i]:
            last_sell = i
        t = b.time.time()
        if t >= square_off:
            if pos != 0:
                ev(b, CLOSE, pos, "EOD")
                pos = 0
            continue
        if line[i] is None or sig[i] is None:
            continue
        bull = (i - last_buy) <= confirm_window and line[i] > sig[i]
        bear = (i - last_sell) <= confirm_window and line[i] < sig[i]
        can_open = t < no_entry
        if bull and pos <= 0:
            if pos == SHORT:
                ev(b, CLOSE, SHORT, "REVERSE")
                pos = 0
            if pos == 0 and can_open:
                ev(b, OPEN, LONG, "ENTRY")
                pos = LONG
        elif bear and pos >= 0:
            if pos == LONG:
                ev(b, CLOSE, LONG, "REVERSE")
                pos = 0
            if pos == 0 and can_open:
                ev(b, OPEN, SHORT, "ENTRY")
                pos = SHORT
    return out
