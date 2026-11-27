"""S4 — Buffer Breakout (strategy-spec-dhansetu-v1).

Reference = previous completed N-minute block's high/low (default 15 min).
Buffer = buffer_pct% of price (or fixed points). On each closed bar:
- close > ref_high + buffer -> OPEN LONG (buy-O)
- close < ref_low  - buffer -> OPEN SHORT (sell-O)
One entry per side per reference block. Exits (SL/TP/EOD) are the execution
engine's job, so this detector emits OPEN events only, edge-triggered per block.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Sequence

from .common import LONG, OPEN, SHORT, SignalEvent, hhmm

NAME = "S4_buffer_breakout"
SESSION_OPEN = dt.time(9, 15)


def _block_index(t: dt.time, block_min: int) -> int:
    mins = (t.hour - 9) * 60 + (t.minute - 15)  # minutes since 09:15
    return mins // block_min


def signals(bars: Sequence, ref_block_minutes: int = 15, buffer_pct: float = 0.1,
            buffer_points: float = None, square_off_ist: str = "1505",
            no_new_entries_ist: str = "1445") -> List[SignalEvent]:
    bars = sorted(bars, key=lambda b: b.time)
    square_off = hhmm(square_off_ist)
    no_entry = hhmm(no_new_entries_ist)
    # high/low per completed block
    block_hi: dict = {}
    block_lo: dict = {}
    out: List[SignalEvent] = []
    fired: set = set()  # (block_index, side)

    for b in bars:
        t = b.time.timetz().replace(tzinfo=None)
        bi = _block_index(t, ref_block_minutes)
        prev = bi - 1
        if t < square_off and t < no_entry and prev in block_hi:
            ref_hi, ref_lo = block_hi[prev], block_lo[prev]
            buf = buffer_points if buffer_points is not None else b.close * buffer_pct / 100.0
            if b.close > ref_hi + buf and (bi, LONG) not in fired:
                out.append(SignalEvent(b.time.isoformat(), OPEN, LONG, b.close, "BREAKOUT", NAME))
                fired.add((bi, LONG))
            elif b.close < ref_lo - buf and (bi, SHORT) not in fired:
                out.append(SignalEvent(b.time.isoformat(), OPEN, SHORT, b.close, "BREAKOUT", NAME))
                fired.add((bi, SHORT))
        # accumulate this bar into its block
        block_hi[bi] = max(block_hi.get(bi, b.high), b.high)
        block_lo[bi] = min(block_lo.get(bi, b.low), b.low)
    return out
