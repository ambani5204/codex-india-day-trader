"""Shared, dependency-free technical indicators for ALGOBANI strategies
(CHG-20261127-2150, strategy-spec-dhansetu-v1).

Pure-Python (no pandas/numpy/TA-Lib) so they run inside the lightweight live
sidecars and in CI. All series functions return a list the SAME length as the
input, with None during the warm-up period, and are computed on CLOSED values
only (no repainting). Standard public definitions:

- sma(n): simple moving average
- ema(n): alpha = 2/(n+1)
- rma(n): Wilder's smoothing, alpha = 1/n (used by RSI and ATR)
- rsi(n): Wilder's RSI
- true_range / atr(n): Wilder ATR
- macd(fast, slow, signal): MACD line, signal line, histogram
- supertrend(period, mult, src=hl2): direction (+1 up / -1 down) and line
- ut_bot(a, c): "UT Bot Alerts" trailing stop + buy/sell cross flags

These match pandas-ta / TradingView conventions; tests in
tests/test_indicators.py pin them to hand-computed values to 1e-9.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Num = Optional[float]


def _need(values: Sequence[float], n: int) -> None:
    if n <= 0:
        raise ValueError("period must be positive")


def sma(values: Sequence[float], n: int) -> List[Num]:
    _need(values, n)
    out: List[Num] = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def ema(values: Sequence[float], n: int) -> List[Num]:
    """EMA seeded with the SMA of the first n values (TradingView/pandas-ta)."""
    _need(values, n)
    out: List[Num] = [None] * len(values)
    if len(values) < n:
        return out
    alpha = 2.0 / (n + 1)
    seed = sum(values[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(values)):
        prev = (values[i] - prev) * alpha + prev
        out[i] = prev
    return out


def rma(values: Sequence[float], n: int) -> List[Num]:
    """Wilder's moving average (RMA), seeded with the first-n SMA."""
    _need(values, n)
    out: List[Num] = [None] * len(values)
    if len(values) < n:
        return out
    alpha = 1.0 / n
    seed = sum(values[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(values)):
        prev = (values[i] - prev) * alpha + prev
        out[i] = prev
    return out


def rsi(closes: Sequence[float], n: int = 14) -> List[Num]:
    """Wilder's RSI. 100 when there are no losses over the window."""
    _need(closes, n)
    out: List[Num] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains[i] = ch if ch > 0 else 0.0
        losses[i] = -ch if ch < 0 else 0.0
    # First average over changes 1..n (Wilder), placed at index n.
    avg_gain = sum(gains[1:n + 1]) / n
    avg_loss = sum(losses[1:n + 1]) / n
    def rsi_val(g, l):
        if l == 0:
            return 100.0 if g > 0 else 50.0
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)
    out[n] = rsi_val(avg_gain, avg_loss)
    for i in range(n + 1, len(closes)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
        out[i] = rsi_val(avg_gain, avg_loss)
    return out


def true_range(highs, lows, closes) -> List[Num]:
    out: List[Num] = [None] * len(closes)
    for i in range(len(closes)):
        if i == 0:
            out[i] = highs[i] - lows[i]
        else:
            out[i] = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i - 1]),
                         abs(lows[i] - closes[i - 1]))
    return out


def atr(highs, lows, closes, n: int = 14) -> List[Num]:
    tr = [x if x is not None else 0.0 for x in true_range(highs, lows, closes)]
    out: List[Num] = [None] * len(closes)
    if len(closes) < n:
        return out
    seed = sum(tr[:n]) / n  # TR[0]=H-L, then n-1 real TRs (Wilder seed)
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(closes)):
        prev = (tr[i] - prev) * (1.0 / n) + prev
        out[i] = prev
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram), each aligned to closes."""
    ef = ema(closes, fast)
    es = ema(closes, slow)
    line: List[Num] = [None] * len(closes)
    for i in range(len(closes)):
        if ef[i] is not None and es[i] is not None:
            line[i] = ef[i] - es[i]
    present = [v for v in line if v is not None]
    sig_compact = ema(present, signal) if present else []
    sig: List[Num] = [None] * len(closes)
    hist: List[Num] = [None] * len(closes)
    j = 0
    for i in range(len(closes)):
        if line[i] is not None:
            s = sig_compact[j] if j < len(sig_compact) else None
            sig[i] = s
            if s is not None:
                hist[i] = line[i] - s
            j += 1
    return line, sig, hist


def supertrend(highs, lows, closes, period: int = 10, mult: float = 3.0):
    """Supertrend on hl2. Returns (direction, line): direction +1 up, -1 down."""
    n = len(closes)
    a = atr(highs, lows, closes, period)
    direction: List[Num] = [None] * n
    line: List[Num] = [None] * n
    final_upper = [None] * n
    final_lower = [None] * n
    prev_dir = 1
    for i in range(n):
        if a[i] is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + mult * a[i]
        basic_lower = hl2 - mult * a[i]
        if final_upper[i - 1] is None:
            fu, fl = basic_upper, basic_lower
            prev_dir = 1
        else:
            fu = basic_upper if (basic_upper < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]) else final_upper[i - 1]
            fl = basic_lower if (basic_lower > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]) else final_lower[i - 1]
        final_upper[i] = fu
        final_lower[i] = fl
        if closes[i] > fu:
            d = 1
        elif closes[i] < fl:
            d = -1
        else:
            d = prev_dir
        prev_dir = d
        direction[i] = d
        line[i] = fl if d == 1 else fu
    return direction, line


def ut_bot(closes: Sequence[float], a: float = 1.0, c: int = 10,
           highs=None, lows=None):
    """UT Bot Alerts trailing stop. Returns (trail, buy, sell) aligned to closes.

    buy[i] True = close crosses above trail; sell[i] True = crosses below.
    ATR uses true range when highs/lows given, else |close diff| (src=close).
    """
    n = len(closes)
    if highs is not None and lows is not None:
        at = atr(highs, lows, closes, c)
    else:
        # ATR of close-only series: TR = |close - prev_close|
        tr = [0.0] + [abs(closes[i] - closes[i - 1]) for i in range(1, n)]
        at = [None] * n
        if n >= c:
            seed = sum(tr[:c]) / c
            at[c - 1] = seed
            prev = seed
            for i in range(c, n):
                prev = (tr[i] - prev) / c + prev
                at[i] = prev
    trail: List[Num] = [None] * n
    buy = [False] * n
    sell = [False] * n
    for i in range(n):
        if at[i] is None:
            continue
        nloss = a * at[i]
        src = closes[i]
        prev_trail = trail[i - 1] if i > 0 else None
        if prev_trail is None:
            trail[i] = src - nloss if True else src + nloss
            continue
        prev_src = closes[i - 1]
        if src > prev_trail and prev_src > prev_trail:
            t = max(prev_trail, src - nloss)
        elif src < prev_trail and prev_src < prev_trail:
            t = min(prev_trail, src + nloss)
        elif src > prev_trail:
            t = src - nloss
        else:
            t = src + nloss
        trail[i] = t
        # cross detection
        if prev_src <= prev_trail and src > t:
            buy[i] = True
        if prev_src >= prev_trail and src < t:
            sell[i] = True
    return trail, buy, sell
