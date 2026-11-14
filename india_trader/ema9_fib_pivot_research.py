"""Research-only 9 EMA + previous-session Fibonacci pivot close-break strategy.

No broker orders. Uses spot-index bars as hypothetical futures-cost proxy.
Previous session OHLC is required; no same-day lookahead.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

from .core import IST
from .research_optimizer import _load_sessions, futures_cost_proxy, _performance


def fibonacci_pivots(bars):
    if not bars:
        raise ValueError("Previous completed session required")
    high = max(b.high for b in bars)
    low = min(b.low for b in bars)
    close = bars[-1].close
    p = (high + low + close) / 3
    span = high - low
    return {"P": p, "R1": p + .382 * span, "R2": p + .618 * span,
            "R3": p + span, "S1": p - .382 * span,
            "S2": p - .618 * span, "S3": p - span}


def signals(bars, previous_bars, rr=2.0, entry_cutoff=dt.time(12, 0)):
    """Require close crossing a pivot AND EMA9 on the same completed 5m bar.

    EMA seeded by SMA9 of current session; prior-day pivot uses only prior OHLC.
    Stop at signal candle opposite extreme; one entry per session.
    Research V2: signals must close before entry_cutoff (default noon IST).
    """
    if rr not in (2.0, 3.0):
        raise ValueError("RR must be 2 or 3")
    if len(bars) < 10:
        return []
    pivots = fibonacci_pivots(previous_bars)
    ema = sum(b.close for b in bars[:9]) / 9
    prior_ema = None
    out = []
    for i, bar in enumerate(bars):
        if i < 9:
            continue
        prior_ema, ema = ema, (bar.close * .2 + ema * .8)
        prev = bars[i - 1]
        if bar.time.date() != bars[0].time.date():
            raise ValueError("Session candles must belong to one date")
        if (bar.time + dt.timedelta(minutes=5)).time() >= entry_cutoff:
            continue
        for name, level in pivots.items():
            bullish = prev.close <= level < bar.close and bar.close > ema and prev.close <= prior_ema
            bearish = prev.close >= level > bar.close and bar.close < ema and prev.close >= prior_ema
            if not (bullish or bearish):
                continue
            direction = "BULL" if bullish else "BEAR"
            entry = bar.close
            stop = bar.low if bullish else bar.high
            risk = abs(entry - stop)
            if risk <= 0:
                continue
            target = entry + (rr * risk if bullish else -rr * risk)
            out.append({"direction": direction, "entry": entry,
                        "stop": stop, "target": target, "risk_points": risk,
                        "pivot": name, "pivot_level": round(level, 4),
                        "ema9": round(ema, 4),
                        "signal_time": (bar.time + dt.timedelta(minutes=5)).isoformat()})
            return out
    return out


def evaluate(sessions, slippage=1.0, entry_cutoff=dt.time(12, 0)):
    """Stop-first when target and stop touch same bar; force EOD exit."""
    by_market = {}
    results = []
    for session in sorted(sessions, key=lambda s: (s["day"], s["market"])):
        market, day = session["market"], session["day"]
        bars = sorted(session["bars"], key=lambda b: b.time)
        prior = by_market.get(market)
        if bars and prior and len(bars) >= 10:
            for rr in (2.0, 3.0):
                found = signals(bars, prior, rr, entry_cutoff=entry_cutoff)
                if not found:
                    continue
                s = found[0]
                direction = s["direction"]
                later = [b for b in bars if b.time >= dt.datetime.fromisoformat(s["signal_time"])]
                if not later:
                    continue
                exit_price = later[-1].close
                reason = "TIME_EXIT"
                for bar in later:
                    hit_stop = bar.low <= s["stop"] if direction == "BULL" else bar.high >= s["stop"]
                    hit_target = bar.high >= s["target"] if direction == "BULL" else bar.low <= s["target"]
                    if hit_stop:
                        exit_price, reason = s["stop"], "STOP"
                        break
                    if hit_target:
                        exit_price, reason = s["target"], "TARGET"
                        break
                # Adverse slippage on entry and exit; no impossible favorable fills.
                entry = s["entry"] + (slippage if direction == "BULL" else -slippage)
                exit_price += (-slippage if direction == "BULL" else slippage)
                points = (exit_price - entry) * (1 if direction == "BULL" else -1)
                risk = abs(entry - s["stop"])
                if risk <= 0:
                    continue
                trade = {"market": market, "day": day.isoformat(),
                         "direction": direction, "entry": entry, "exit": exit_price,
                         "index_points": points, "risk_points": risk,
                         "realized_r": points / risk, "rr": rr,
                         "pivot": s["pivot"], "exit_reason": reason,
                         "entry_time": s["signal_time"]}
                results.append(futures_cost_proxy(trade))
        if bars:
            by_market[market] = bars
    output = {}
    for rr in (2.0, 3.0):
        subset = [t for t in results if t["rr"] == rr]
        output[f"RR_{int(rr)}"] = {"metrics": _performance(subset),
                                    "trades": subset}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--entry-cutoff", default="12:00", help="Last allowed signal close time in IST, HH:MM (V2 default 12:00; baseline 14:45)")
    parser.add_argument("--days", type=int, default=365, help="Completed calendar days to examine (default 365)")
    args = parser.parse_args()
    try:\n        cutoff = dt.time.fromisoformat(args.entry_cutoff)\n    except ValueError:\n        parser.error("--entry-cutoff must be HH:MM")
    end = dt.datetime.now(IST).date() - dt.timedelta(days=1)
    if not 30 <= args.days <= 730:
        parser.error("--days must be between 30 and 730")
    start = end - dt.timedelta(days=args.days - 1)
    report = {"kind": "EMA9_FIB_PIVOT_PAPER_RESEARCH_ONLY",
              "status": "AWAITING_MARKET_DATA", "results": {},
              "start_date": start.isoformat(), "end_date": end.isoformat(),
              "warning": "Spot index / hypothetical futures-cost proxy; NOT options P&L"}
    if end >= start:
        sessions = _load_sessions(start, end, "BOTH", __import__(
            "india_trader.index_intraday_backtest", fromlist=["_LazyHistoricalReader"]
        )._LazyHistoricalReader(), "trader/backtest_cache")
        report["results"] = evaluate(sessions, entry_cutoff=cutoff)
        report["entry_cutoff_ist"] = cutoff.isoformat()
        report["session_count"] = sum(bool(x["bars"]) for x in sessions)
        report["markets"] = ["NIFTY", "SENSEX"]
        report["status"] = "RESEARCH_ONLY_NOT_DEPLOYMENT_APPROVAL"
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print("EMA9_FIB_PIVOT_RESEARCH", report["status"])


if __name__ == "__main__":
    main()
