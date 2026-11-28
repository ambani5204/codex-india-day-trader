"""S6 — Equity long-term RSI-MA > 40 scanner (spec §S6). Buy-only.

Daily timeframe. RSI(14) smoothed by SMA(RSI, 14) = RSI-MA. Buy when RSI-MA
crosses above the threshold (default 40) and holds for `confirm` closes; exit
(CLOSE long) when RSI-MA falls back below. No shorts, no intraday time gates —
this is a daily positional scanner.

Pure function; downstream decides whether to paper-track or log signals only.
"""
from __future__ import annotations

from typing import List, Sequence

from .. import indicators as ind
from .common import CLOSE, LONG, OPEN, SignalEvent

NAME = "S6_equity_rsima_scanner"


def signals(bars: Sequence, rsi_n: int = 14, ma_n: int = 14,
            threshold: float = 40.0, confirm: int = 1) -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    closes = [b.close for b in bars]
    rsi = ind.rsi(closes, rsi_n)
    present = [v for v in rsi if v is not None]
    ma_compact = ind.sma(present, ma_n) if present else []
    # realign RSI-MA to bars
    rsima: List = [None] * len(bars)
    j = 0
    for i in range(len(bars)):
        if rsi[i] is not None:
            rsima[i] = ma_compact[j] if j < len(ma_compact) else None
            j += 1

    out: List[SignalEvent] = []
    pos = 0
    above_streak = 0

    def ev(b, action, side, reason):
        out.append(SignalEvent(b.time.isoformat(), action, side, b.close, reason, NAME))

    for i, b in enumerate(bars):
        if rsima[i] is None:
            continue
        above = rsima[i] > threshold
        above_streak = above_streak + 1 if above else 0
        if pos == 0 and above_streak >= confirm:
            ev(b, OPEN, LONG, "RSIMA_ABOVE")
            pos = LONG
        elif pos == LONG and not above:
            ev(b, CLOSE, LONG, "RSIMA_BELOW")
            pos = 0
    return out
