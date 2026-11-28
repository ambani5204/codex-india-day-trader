"""S8 Phase — out-of-sample walk-forward qualification (spec: options-only OOS,
walk-forward, FROZEN qualification thresholds, 60% aspirational win target).

A strategy earns live-paper trust only if it clears FROZEN thresholds on
OUT-OF-SAMPLE windows it was never tuned on. This module rolls train/test
windows over a session series and runs each strategy's metrics on the TEST
(OOS) windows only, then applies the frozen gate. Pure/deterministic; metrics
come from backtest.metrics_from_closes on real-candle paper closes upstream.

The thresholds are frozen constants here so they cannot be quietly relaxed to
make a strategy pass — changing them is a visible code change under the gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence

# 60% is the ASPIRATIONAL win target (spec). The hard qualification floor is
# lower and paired with profit-factor and drawdown so a high win rate alone
# (e.g. many tiny wins, few huge losses) cannot qualify a losing strategy.
ASPIRATIONAL_WIN_RATE = 60.0


@dataclass(frozen=True)
class Thresholds:
    min_oos_windows: int = 3        # must survive this many OOS windows
    min_trades_per_window: int = 3
    min_win_rate_pct: float = 45.0  # hard floor (< aspirational 60)
    min_profit_factor: float = 1.2
    max_drawdown: float = 9000.0    # rupees; survivable for ~Rs15k capital
    min_net_pnl: float = 0.0        # OOS must not lose overall


FROZEN = Thresholds()


@dataclass
class WindowResult:
    index: int
    metrics: dict
    passed: bool
    reasons: List[str]


def rolling_windows(n_sessions: int, train: int, test: int, step: int = None):
    """Yield (train_slice, test_slice) index ranges. test is the OOS part."""
    step = step or test
    i = 0
    while i + train + test <= n_sessions:
        yield (range(i, i + train), range(i + train, i + train + test))
        i += step


def qualify_window(metrics: dict, th: Thresholds = FROZEN) -> WindowResult:
    reasons = []
    if metrics.get("trades", 0) < th.min_trades_per_window:
        reasons.append(f"trades<{th.min_trades_per_window}")
    wr = metrics.get("win_rate_pct")
    if wr is None or wr < th.min_win_rate_pct:
        reasons.append(f"win_rate<{th.min_win_rate_pct}")
    pf = metrics.get("profit_factor")
    if pf is None or pf < th.min_profit_factor:
        reasons.append(f"profit_factor<{th.min_profit_factor}")
    if metrics.get("max_drawdown", 1e9) > th.max_drawdown:
        reasons.append(f"drawdown>{th.max_drawdown}")
    if metrics.get("net_pnl", -1) < th.min_net_pnl:
        reasons.append(f"net_pnl<{th.min_net_pnl}")
    return WindowResult(-1, metrics, not reasons, reasons)


def evaluate(sessions: Sequence, metric_fn: Callable[[Sequence], dict],
             train: int, test: int, step: int = None, th: Thresholds = FROZEN) -> dict:
    """sessions: list of per-session closed-trade lists (one per trading day).
    metric_fn: maps a concatenated list of closed trades -> metrics dict.
    Returns the OOS verdict: qualified only if enough OOS windows pass."""
    windows = []
    for wi, (_, test_idx) in enumerate(rolling_windows(len(sessions), train, test, step)):
        oos_trades = []
        for j in test_idx:
            oos_trades.extend(sessions[j])
        res = qualify_window(metric_fn(oos_trades), th)
        res.index = wi
        windows.append(res)
    passed = [w for w in windows if w.passed]
    qualified = len(windows) >= th.min_oos_windows and len(passed) == len(windows) and windows != []
    return {
        "windows": len(windows),
        "passed_windows": len(passed),
        "qualified": qualified,
        "aspirational_win_rate": ASPIRATIONAL_WIN_RATE,
        "thresholds": th.__dict__,
        "detail": [{"window": w.index, "passed": w.passed,
                    "reasons": w.reasons, "metrics": w.metrics} for w in windows],
    }
