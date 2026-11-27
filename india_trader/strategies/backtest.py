"""Backtest harness for ALGOBANI strategies (strategy-spec-dhansetu-v1).

Runs a strategy detector + the paper execution engine over a series of index
bars using an injected option-quote provider, and computes the standard
metrics: trades, win rate, net P&L, gross P&L, max drawdown, profit factor,
average realised RR, and fees paid.

IMPORTANT: the metrics are only as real as the inputs. Fed REAL historical
index + option-premium data, these are real backtest results. Fed synthetic or
modelled premiums, they are mechanics only and must never be reported as a real
edge. This module computes; it does not fabricate data.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Sequence

from .common import OPEN, SignalEvent
from .paper_exec import PaperExecutionEngine, RiskParams


def metrics_from_closes(closed_trades: List[dict]) -> dict:
    """closed_trades: engine audit rows with action=='CLOSE' (have net_pnl, gross_pnl, fees)."""
    if not closed_trades:
        return {"trades": 0, "wins": 0, "win_rate_pct": None, "net_pnl": 0.0,
                "gross_pnl": 0.0, "fees": 0.0, "max_drawdown": 0.0,
                "profit_factor": None, "avg_rr": None}
    nets = [t["net_pnl"] for t in closed_trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    # equity curve + max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for n in nets:
        equity += n
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    # realised RR per trade = reward/risk magnitude vs entry; approx from premium move
    rrs = []
    for t in closed_trades:
        move = t.get("exit_premium", 0) - t.get("entry_premium", 0)
        rrs.append(abs(move))
    return {
        "trades": len(nets),
        "wins": len(wins),
        "win_rate_pct": round(100 * len(wins) / len(nets), 1),
        "net_pnl": round(sum(nets), 2),
        "gross_pnl": round(sum(t["gross_pnl"] for t in closed_trades), 2),
        "fees": round(sum(t["fees"] for t in closed_trades), 2),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "avg_abs_premium_move": round(sum(rrs) / len(rrs), 2) if rrs else None,
    }


def run_session(detector_signals: List[SignalEvent], bars: Sequence, provider,
                underlying: str, risk: RiskParams, square_off_ist: str = "1505") -> List[dict]:
    """Replay one session: feed signals at their bars, tick the engine each bar."""
    eng = PaperExecutionEngine(provider, square_off_ist)
    key = f"{detector_signals[0].strategy}|{underlying}" if detector_signals else None
    if risk.day_max_loss is not None or risk.day_max_profit is not None:
        eng.set_day_caps(detector_signals[0].strategy, underlying,
                         risk.day_max_loss, risk.day_max_profit)
    sig_by_time: Dict[str, List[SignalEvent]] = {}
    for s in detector_signals:
        sig_by_time.setdefault(s.bar_time, []).append(s)
    risk_by = {f"{s.strategy}|{underlying}": risk for s in detector_signals}
    for b in sorted(bars, key=lambda x: x.time):
        now = b.time
        if hasattr(provider, "set"):
            provider.set(b.close, now)
        for s in sig_by_time.get(b.time.isoformat(), []):
            eng.on_signal(s, underlying, risk, now)
        eng.on_tick(now, risk_by)
    # force EOD close at the last bar's session end
    if bars:
        last = sorted(bars, key=lambda x: x.time)[-1].time
        eod = last.replace(hour=int(square_off_ist[:2]), minute=int(square_off_ist[2:]),
                           second=0, microsecond=0)
        if hasattr(provider, "set"):
            provider.set(sorted(bars, key=lambda x: x.time)[-1].close, eod)
        eng.on_tick(eod, risk_by)
    return [a for a in eng.audit if a["action"] == "CLOSE"]
