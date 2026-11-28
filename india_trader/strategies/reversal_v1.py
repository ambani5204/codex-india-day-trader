"""S7 — Algobani Reversal v1 (spec §S7): price action at support/resistance.

Concrete, testable reversal rule on CLOSED 5-min bars:
- Levels: previous-day high/low/close (from bars dated before today) + today's
  opening-range high/low (09:15-10:00). Merged within merge_pct.
- Long: bar.low tags a level (within tag_pct) AND close > level AND the candle
  is a bullish rejection (lower wick >= wick_body_ratio x body). Short mirror at
  resistance (high tags level, close < level, upper wick >= ratio x body).
- One position at a time, max_trades/day, 15:05 square-off.

Pure function; option pricing and SL/TP handled by the execution layer.
"""
from __future__ import annotations

from typing import List, Sequence

from .common import CLOSE, LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S7_reversal_v1"


def _merge(levels, merge_pct):
    levels = sorted(set(levels))
    out = []
    for lv in levels:
        if out and abs(lv - out[-1]) / out[-1] <= merge_pct:
            continue
        out.append(lv)
    return out


def signals(bars: Sequence, tag_pct: float = 0.0005, merge_pct: float = 0.001,
            wick_body_ratio: float = 2.0, max_trades: int = 3,
            range_start_ist: str = "0915", range_end_ist: str = "1000",
            square_off_ist: str = "1505", no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    if not bars:
        return []
    today = bars[-1].time.date()
    r_start, r_end = hhmm(range_start_ist), hhmm(range_end_ist)
    square_off, no_entry = hhmm(square_off_ist), hhmm(no_new_entries_ist)

    prev = [b for b in bars if b.time.date() < today]
    levels = []
    if prev:
        levels += [max(b.high for b in prev), min(b.low for b in prev), prev[-1].close]
    orb_hi = orb_lo = None
    for b in bars:
        if b.time.date() == today and r_start <= b.time.time() < r_end:
            orb_hi = b.high if orb_hi is None else max(orb_hi, b.high)
            orb_lo = b.low if orb_lo is None else min(orb_lo, b.low)
    if orb_hi is not None:
        levels += [orb_hi, orb_lo]
    levels = _merge([lv for lv in levels if lv and lv > 0], merge_pct)

    out: List[SignalEvent] = []
    pos = 0
    trades = 0

    def ev(b, action, side, reason):
        out.append(SignalEvent(b.time.isoformat(), action, side, b.close, reason, NAME))

    for b in bars:
        if b.time.date() != today:
            continue
        t = b.time.time()
        if t >= square_off:
            if pos != 0:
                ev(b, CLOSE, pos, "EOD")
                pos = 0
            continue
        if t < r_end or pos != 0 or trades >= max_trades or t >= no_entry:
            continue
        body = abs(b.close - b.open) or 1e-9
        lower_wick = min(b.open, b.close) - b.low
        upper_wick = b.high - max(b.open, b.close)
        for lv in levels:
            if abs(b.low - lv) / lv <= tag_pct and b.close > lv and lower_wick >= wick_body_ratio * body:
                ev(b, OPEN, LONG, "SUPPORT_REJECT")
                pos = LONG
                trades += 1
                break
            if abs(b.high - lv) / lv <= tag_pct and b.close < lv and upper_wick >= wick_body_ratio * body:
                ev(b, OPEN, SHORT, "RESIST_REJECT")
                pos = SHORT
                trades += 1
                break
    return out
