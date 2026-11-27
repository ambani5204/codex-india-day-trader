"""Shared types for ALGOBANI strategy signal detection (strategy-spec-dhansetu-v1).

Detectors are PURE functions over CLOSED bars: they emit ordered signal events
and never fetch quotes, size positions or place orders. The paper execution
layer consumes these events, prices the ATM option, and manages SL/TP/trail/
EOD/kill with full audit — keeping signal logic testable in isolation.

Signal grammar (options BUYING only): a reversal is emitted as a CLOSE event
then an OPEN event on the same bar, which composes the spec's sell-C_O / buy-C_O.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

OPEN = "OPEN"
CLOSE = "CLOSE"
LONG = 1
SHORT = -1


@dataclass(frozen=True)
class SignalEvent:
    bar_time: str      # ISO timestamp of the closed bar that produced it
    action: str        # OPEN | CLOSE
    side: int          # LONG(+1) = CE, SHORT(-1) = PE
    price: float       # underlying signal price (bar close)
    reason: str        # e.g. ENTRY, REVERSE, EOD, SIGNAL
    strategy: str

    def grammar(self) -> str:
        if self.action == OPEN:
            return "buy-O" if self.side == LONG else "sell-O"
        return "sell-C" if self.side == LONG else "buy-C"  # close of a long / short


def hhmm(t: str) -> dt.time:
    return dt.time(int(t[:2]), int(t[2:]))
