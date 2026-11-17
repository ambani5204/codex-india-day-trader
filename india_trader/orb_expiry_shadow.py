"""Paper-only ORB candidate routing. No broker orders or simulated option fills.

Candidate observations are derived from closed-bar index signals; no P&L is
reported until executable historical/live option quotes and margin are verified.
"""
from __future__ import annotations
import datetime as dt
import json
import sys

CONFIG = {
    "NIFTY": {"opening_minutes": 60, "confirmation_minutes": 5, "target_r": 3.0},
    "SENSEX": {"opening_minutes": 45, "confirmation_minutes": 15, "target_r": 3.0},
}

def route(market: str, direction: str, expiry_today: bool, candle_high: float,
          candle_low: float, entry: float, buffer_points: float = 0.0) -> dict:
    if market not in CONFIG or direction not in ("BULL", "BEAR"):
        raise ValueError("Unsupported market/direction")
    if not all(isinstance(x, (int, float)) and x > 0 for x in (candle_high, candle_low, entry)):
        raise ValueError("Invalid candle/entry")
    if not 0 <= buffer_points < entry or candle_low > candle_high:
        raise ValueError("Invalid candle or buffer")
    stop = candle_low - buffer_points if direction == "BULL" else candle_high + buffer_points
    risk = entry - stop if direction == "BULL" else stop - entry
    if risk <= 0:
        raise ValueError("Candle stop invalidates trade; skip")
    mode = ("SELL_PE_HEDGED_CREDIT_SPREAD" if direction == "BULL" else
            "SELL_CE_HEDGED_CREDIT_SPREAD") if expiry_today else (
            "BUY_CE" if direction == "BULL" else "BUY_PE")
    return {
        "market": market, "direction": direction, "candidate": CONFIG[market],
        "expiry_today": bool(expiry_today), "proposed_execution": mode,
        "underlying_entry": entry, "underlying_candle_stop": stop,
        "underlying_target": entry + (risk * CONFIG[market]["target_r"] *
                                      (1 if direction == "BULL" else -1)),
        "status": "OBSERVATION_ONLY_NO_OPTION_FILL",
        "requires": ["timestamped option quotes", "contract and lot selection",
                     "bid/ask slippage and fees", "margin check",
                     "premium-based risk exit", "liquidity check"],
        "real_orders": False,
    }

def self_test():
    a = route("NIFTY", "BULL", True, 25510, 25490, 25520)
    assert a["proposed_execution"] == "SELL_PE_HEDGED_CREDIT_SPREAD"
    assert a["underlying_candle_stop"] == 25490
    b = route("SENSEX", "BEAR", False, 82020, 81980, 81970)
    assert b["proposed_execution"] == "BUY_PE"
    assert b["underlying_target"] < b["underlying_entry"]
    try:
        route("NIFTY", "BULL", False, 25510, 25490, 25480)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid stop must reject")
    print("ORB shadow routing tests passed")

if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        raise SystemExit("Only --self-test is supported; no live option execution implemented")
