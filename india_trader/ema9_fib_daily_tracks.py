"""Daily research intents for EMA9 Fibonacci V2, never executable broker orders.

Option buying/selling require real option quotes, strike, expiry, lot, fees and
selling margin before a trade can be marked filled or assigned P&L.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from .core import IST
from .ema9_fib_pivot_research import signals
from .research_optimizer import _load_sessions
from .index_intraday_backtest import _LazyHistoricalReader

TRACKS = ("OPTION_BUY", "OPTION_SELL", "INDEX_INTRADAY")

def daily_intents(sessions, date):
    previous = {}
    out = []
    for session in sorted(sessions, key=lambda s: (s["day"], s["market"])):
        market, day = session["market"], session["day"]
        bars = sorted(session["bars"], key=lambda b: b.time)
        prior = previous.get(market)
        if day == date and bars and prior:
            for rr in (2.0, 3.0):
                for signal in signals(bars, prior, rr=rr):
                    side = signal["direction"]
                    for track in TRACKS:
                        if track == "OPTION_BUY":
                            instrument = "CE" if side == "BULL" else "PE"
                            action = "BUY"
                        elif track == "OPTION_SELL":
                            instrument = "PE" if side == "BULL" else "CE"
                            action = "SELL"
                        else:
                            instrument = "INDEX_POINT_PROXY"
                            action = "LONG" if side == "BULL" else "SHORT"
                        out.append({
                            "date_ist": day.isoformat(), "market": market,
                            "strategy": "EMA9_FIB_PIVOT_V2",
                            "track": track, "action": action,
                            "instrument_type": instrument, "rr": rr,
                            "signal": signal, "execution_status": "SIGNAL_ONLY",
                            "data_type": "RESEARCH_SIGNAL_NOT_EXECUTED",
                            "net_pnl_inr": None,
                            "reason": ("Historical option contract quotes and margin validation required"
                                       if track != "INDEX_INTRADAY"
                                       else "Index levels are not executable orders"),
                        })
        if bars:
            previous[market] = bars
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=None, help="Completed market day YYYY-MM-DD")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    now = dt.datetime.now(IST)
    date = (dt.date.fromisoformat(args.day) if args.day else
            (now.date() if now.time() >= dt.time(16, 0)
             else now.date() - dt.timedelta(days=1)))
    sessions = _load_sessions(date-dt.timedelta(days=12), date, "BOTH",
                              _LazyHistoricalReader(), "trader/backtest_cache")
    output = {
        "kind": "EMA9_FIB_V2_DAILY_MULTI_TRACK_RESEARCH",
        "date_ist": date.isoformat(),
        "markets": ["NIFTY", "SENSEX"],
        "tracks": list(TRACKS),
        "paper_execution_enabled": False,
        "real_order_execution_enabled": False,
        "option_pnl_available": False,
        "intents": daily_intents(sessions, date),
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, default=str)+"\n")
    print("DAILY_RESEARCH_SIGNALS", len(output["intents"]))

if __name__ == "__main__":
    main()
