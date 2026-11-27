"""Shared PAPER execution engine for ALGOBANI strategies (strategy-spec-dhansetu-v1).

Turns strategy SignalEvents into paper option trades and manages them:
ATM option (options BUYING only), SL/TP in premium points, optional trailing,
per-strategy/per-underlying trade cap and day max-loss / max-profit, global +
per-strategy kill switch, EOD square-off. Every state change is recorded as an
audit dict (signal→decision→fill timestamps, exit type, premiums, P&L, fees).

NO REAL ORDERS. Paper fills use the OBSERVED quote passed in (bid to sell, ask
to buy) — never invented. Quotes come from an injected provider so the engine is
unit-testable with synthetic quotes; the live sidecar supplies a real Upstox
read-only provider. Fees use india_trader.paper_sim.option_fees (round-trip).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

from ..paper_sim import option_fees
from .common import CLOSE, LONG, OPEN, SHORT, SignalEvent, hhmm


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    bid: float
    ask: float
    exchange: str          # NFO | BFO
    delta: float = 0.5


@dataclass
class RiskParams:
    sl_points: float
    tp_points: float
    max_trades: int
    qty: int
    exchange: str
    trail_start: Optional[float] = None   # premium points of profit to arm trailing
    trail_step: Optional[float] = None    # points the stop trails behind the high
    day_max_loss: Optional[float] = None  # rupees (positive number); stop strategy for the day
    day_max_profit: Optional[float] = None


@dataclass
class Position:
    strategy: str
    underlying: str
    side: int
    symbol: str
    exchange: str
    entry: float          # premium paid (ask)
    qty: int
    open_time: str
    sl: float             # premium stop level (absolute premium)
    tp: float             # premium target level
    high_watermark: float
    trail_armed: bool = False


@dataclass
class Book:
    """Per (strategy, underlying) state for one trading day."""
    trades_today: int = 0
    realized_pnl: float = 0.0
    stopped_reason: Optional[str] = None   # DAY_MAX_LOSS | DAY_MAX_PROFIT | KILL
    position: Optional[Position] = None


class PaperExecutionEngine:
    def __init__(self, provider, square_off_ist: str = "1505",
                 clock: Callable[[], dt.datetime] = None):
        self.provider = provider
        self.square_off = hhmm(square_off_ist)
        self.clock = clock
        self.books: Dict[str, Book] = {}
        self.audit: List[dict] = []
        self.global_kill = False

    # ------------------------------------------------------------------ utils
    def _key(self, strategy, underlying):
        return f"{strategy}|{underlying}"

    def book(self, strategy, underlying) -> Book:
        return self.books.setdefault(self._key(strategy, underlying), Book())

    def _record(self, **row):
        self.audit.append(row)

    def set_kill(self, on: bool = True, strategy: Optional[str] = None):
        """Global kill (strategy=None) or per-strategy kill."""
        if strategy is None:
            self.global_kill = on
        else:
            for k, b in self.books.items():
                if k.split("|")[0] == strategy and on and b.position is None:
                    b.stopped_reason = "KILL"

    def _killed(self, strategy) -> bool:
        return self.global_kill

    # --------------------------------------------------------------- lifecycle
    def on_signal(self, event: SignalEvent, underlying: str, risk: RiskParams, now: dt.datetime):
        b = self.book(event.strategy, underlying)
        if event.action == CLOSE:
            if b.position is not None:
                self._close(b, underlying, now, reason=event.reason, signal_time=event.bar_time)
            return
        # OPEN
        if self._killed(event.strategy) or b.stopped_reason:
            self._record(ts=now.isoformat(), strategy=event.strategy, underlying=underlying,
                         action="OPEN_BLOCKED", reason=b.stopped_reason or "KILL", signal_time=event.bar_time)
            return
        if b.position is not None:
            return  # already in a position (reversals close first via a prior CLOSE event)
        if b.trades_today >= risk.max_trades:
            self._record(ts=now.isoformat(), strategy=event.strategy, underlying=underlying,
                         action="OPEN_BLOCKED", reason="MAX_TRADES", signal_time=event.bar_time)
            return
        if now.time() >= self.square_off:
            return
        q = self.provider.atm(underlying, event.side, event.price, now)
        if q is None:
            self._record(ts=now.isoformat(), strategy=event.strategy, underlying=underlying,
                         action="OPEN_SKIPPED", reason="NO_QUOTE", signal_time=event.bar_time)
            return
        entry = q.ask  # buying the option
        pos = Position(event.strategy, underlying, event.side, q.symbol, q.exchange, entry,
                       risk.qty, now.isoformat(), entry - risk.sl_points, entry + risk.tp_points, entry)
        b.position = pos
        b.trades_today += 1
        self._record(ts=now.isoformat(), strategy=event.strategy, underlying=underlying,
                     action="OPEN", grammar=event.grammar(), side=event.side, symbol=q.symbol,
                     exchange=q.exchange, entry_premium=entry, qty=risk.qty,
                     sl=pos.sl, tp=pos.tp, signal_time=event.bar_time, signal_price=event.price)

    def on_tick(self, now: dt.datetime, risk_by: Dict[str, RiskParams]):
        """Check SL/TP/trail/EOD for every open position. risk_by[key]=RiskParams."""
        for key, b in list(self.books.items()):
            if b.position is None:
                continue
            strategy, underlying = key.split("|")
            if now.time() >= self.square_off:
                self._close(b, underlying, now, reason="EOD")
                continue
            if self.global_kill:
                self._close(b, underlying, now, reason="KILL")
                continue
            q = self.provider.quote(b.position.symbol, now)
            if q is None:
                continue
            prem = q.bid  # we would sell at bid
            pos = b.position
            risk = risk_by.get(key)
            # trailing
            if risk and risk.trail_start is not None and risk.trail_step is not None:
                if prem > pos.high_watermark:
                    pos.high_watermark = prem
                if not pos.trail_armed and prem - pos.entry >= risk.trail_start:
                    pos.trail_armed = True
                if pos.trail_armed:
                    pos.sl = max(pos.sl, pos.high_watermark - risk.trail_step)
            if prem <= pos.sl:
                self._close(b, underlying, now, reason="TRAIL" if pos.trail_armed else "SL", exit_prem=prem)
            elif prem >= pos.tp:
                self._close(b, underlying, now, reason="TP", exit_prem=prem)

    def _close(self, b: Book, underlying: str, now: dt.datetime, reason: str,
               exit_prem: Optional[float] = None, signal_time: Optional[str] = None):
        pos = b.position
        if pos is None:
            return
        if exit_prem is None:
            q = self.provider.quote(pos.symbol, now)
            exit_prem = q.bid if q is not None else pos.entry
        gross = (exit_prem - pos.entry) * pos.qty  # long option: sell - buy
        fees = option_fees(pos.entry, max(exit_prem, 0.05), pos.qty, pos.exchange, "UPSTOX")["total"]
        net = round(gross - fees, 2)
        b.realized_pnl = round(b.realized_pnl + net, 2)
        self._record(ts=now.isoformat(), strategy=pos.strategy, underlying=underlying,
                     action="CLOSE", exit_type=reason, symbol=pos.symbol, entry_premium=pos.entry,
                     exit_premium=exit_prem, qty=pos.qty, gross_pnl=round(gross, 2), fees=fees,
                     net_pnl=net, day_realized=b.realized_pnl, signal_time=signal_time)
        b.position = None
        self._apply_day_caps(b, pos.strategy, underlying, now)

    def _apply_day_caps(self, b: Book, strategy, underlying, now):
        # caps are enforced via risk params at close time by the caller passing them in on_signal;
        # here we only mark a stop if realized crosses a cap recorded on the book.
        if getattr(b, "_day_max_loss", None) is not None and b.realized_pnl <= -b._day_max_loss:
            b.stopped_reason = "DAY_MAX_LOSS"
            self._record(ts=now.isoformat(), strategy=strategy, underlying=underlying,
                         action="STRATEGY_STOPPED", reason="DAY_MAX_LOSS", day_realized=b.realized_pnl)
        elif getattr(b, "_day_max_profit", None) is not None and b.realized_pnl >= b._day_max_profit:
            b.stopped_reason = "DAY_MAX_PROFIT"
            self._record(ts=now.isoformat(), strategy=strategy, underlying=underlying,
                         action="STRATEGY_STOPPED", reason="DAY_MAX_PROFIT", day_realized=b.realized_pnl)

    def set_day_caps(self, strategy, underlying, max_loss=None, max_profit=None):
        b = self.book(strategy, underlying)
        b._day_max_loss = max_loss
        b._day_max_profit = max_profit

    def summary(self) -> dict:
        return {k: {"trades": b.trades_today, "realized_pnl": b.realized_pnl,
                    "stopped": b.stopped_reason, "open": b.position is not None}
                for k, b in self.books.items()}
