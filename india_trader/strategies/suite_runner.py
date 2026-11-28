"""Multi-strategy paper suite runner (owner mandate: run all strategies always).

Routes each enabled closed-bar detector's signals into one shared
PaperExecutionEngine, so S2/S4/S5 all trade the same session in paper, each on
its own (strategy, market) book. The core `step()` loop is pure and fully
testable with a fake quote provider; the live Upstox adapter is a thin wrapper
built separately (suite_live_sidecar). PAPER ONLY — never places real orders.

Only detectors that actually exist are wired. S1/S3/S6/S7 in config have no
detector yet and therefore cannot run until one is written.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from india_trader.strategies import (buffer_breakout, orb, reversal_v1, rsima_scanner,
                                      sma_rsi, supertrend_sma, utbot_macd)
from india_trader.strategies.common import CLOSE
from india_trader.strategies.paper_exec import PaperExecutionEngine, RiskParams

# All seven spec strategies now have detectors. Maps strategy key -> signal fn.
DETECTORS = {
    orb.NAME: orb.signals,                      # S1
    supertrend_sma.NAME: supertrend_sma.signals,  # S2
    utbot_macd.NAME: utbot_macd.signals,        # S3
    buffer_breakout.NAME: buffer_breakout.signals,  # S4
    sma_rsi.NAME: sma_rsi.signals,              # S5
    rsima_scanner.NAME: rsima_scanner.signals,  # S6 (daily scanner)
    reversal_v1.NAME: reversal_v1.signals,      # S7
}
AVAILABLE = tuple(DETECTORS)
NO_DETECTOR_YET = ()  # all S1-S7 implemented
# S6 is a daily positional scanner; the intraday suite enables S1-S5 + S7 by default.
INTRADAY = tuple(n for n in DETECTORS if n != rsima_scanner.NAME)


class SuiteRunner:
    """Feed growing bars per market; dispatch each enabled detector's NEW events."""

    def __init__(self, engine: PaperExecutionEngine, enabled: Sequence[str],
                 risk_by_strategy: Dict[str, RiskParams]):
        unknown = set(enabled) - set(DETECTORS)
        if unknown:
            raise ValueError(f"no detector implemented for: {sorted(unknown)} "
                             f"(available: {sorted(DETECTORS)})")
        self.engine = engine
        self.enabled = list(enabled)
        self.risk_by_strategy = risk_by_strategy
        self._seen: Dict[str, int] = {}   # per (strategy,market) count of dispatched events

    def step(self, market: str, bars: Sequence, now) -> None:
        """Dispatch any signals newly produced by the closed bars seen so far."""
        risk_tick = {}
        for strat in self.enabled:
            events = DETECTORS[strat](bars)
            key = f"{strat}|{market}"
            start = self._seen.get(key, 0)
            for ev in events[start:]:
                self.engine.on_signal(ev, market, self.risk_by_strategy[strat], now)
            self._seen[key] = len(events)
            risk_tick[f"{strat}|{market}"] = self.risk_by_strategy[strat]
        # SL/TP/trail/EOD housekeeping for every open book in this market.
        self.engine.on_tick(now, risk_tick)

    def close_all(self, now) -> None:
        """EOD flat: emit a CLOSE for any still-open book."""
        for key, book in list(self.engine.books.items()):
            if book.position is not None:
                strat, market = key.split("|")
                from india_trader.strategies.common import SignalEvent
                self.engine.on_signal(
                    SignalEvent(now.isoformat(), CLOSE, book.position.side,
                                book.position.entry, "EOD", strat),
                    market, self.risk_by_strategy[strat], now)


def resolve_enabled(raw: str) -> List[str]:
    """Parse ALGOBANI_ENABLE_STRATEGIES. 'ALL'/'' -> every INTRADAY detector.

    S6 is a daily scanner and is excluded from the intraday live suite; name it
    explicitly to include it, or run it via the daily-scan path.
    """
    raw = (raw or "").strip()
    if raw.upper() in ("", "ALL"):
        return list(INTRADAY)
    wanted = [x.strip() for x in raw.split(",") if x.strip()]
    return [w for w in wanted if w in DETECTORS]
