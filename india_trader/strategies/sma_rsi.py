"""S5 — SMA + RSI (strategy-spec-dhansetu-v1).

On CLOSED bars of the strategy timeframe (15-min intraday default):
- Long  when close > SMA(n) AND RSI(r) > rsi_long
- Short when close < SMA(n) AND RSI(r) < rsi_short
Edge-triggered: one OPEN per transition into the condition; exits (SL/TP/EOD)
belong to the execution engine. Bars are expected already at the strategy
timeframe (the sidecar resamples 5-min -> 15-min).
"""
from __future__ import annotations

from typing import List, Sequence

from .. import indicators as ind
from .common import LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S5_sma_rsi"


def signals(bars: Sequence, sma_n: int = 20, rsi_n: int = 14,
            rsi_long: float = 55.0, rsi_short: float = 45.0,
            square_off_ist: str = "1505", no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    closes = [b.close for b in bars]
    sma = ind.sma(closes, sma_n)
    rsi = ind.rsi(closes, rsi_n)
    square_off = hhmm(square_off_ist)
    no_entry = hhmm(no_new_entries_ist)

    out: List[SignalEvent] = []
    prev_state = 0  # last emitted side state to edge-trigger
    for i, b in enumerate(bars):
        if sma[i] is None or rsi[i] is None:
            continue
        t = b.time.astimezone(b.time.tzinfo).time()
        long_cond = closes[i] > sma[i] and rsi[i] > rsi_long
        short_cond = closes[i] < sma[i] and rsi[i] < rsi_short
        state = LONG if long_cond else SHORT if short_cond else 0
        if state != 0 and state != prev_state and t < square_off and t < no_entry:
            out.append(SignalEvent(b.time.isoformat(), OPEN, state, b.close, "ENTRY", NAME))
        prev_state = state
    return out
