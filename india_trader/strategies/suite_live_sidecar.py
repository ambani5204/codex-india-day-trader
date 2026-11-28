"""Live PAPER sidecar that runs the whole implemented strategy suite (S2/S4/S5).

Owner mandate: run all strategies always (paper). This is the live wiring for
SuiteRunner. It is ENV-GATED: it only runs when RUN_STRATEGY_SUITE=1, so it does
NOT touch the Monday two-job validation unless explicitly switched on. Isolated
journal (trader/strategy_suite_live/<date>.jsonl); never submits broker orders.

The pure routing is tested in tests/test_suite_runner.py. This file is the thin,
offline-untestable Upstox glue (real candles + ATM selection + fresh quotes).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

from india_trader.core import IST, env_time
from india_trader.strategies.paper_exec import OptionQuote, PaperExecutionEngine, RiskParams
from india_trader.strategies.common import LONG
from india_trader.strategies.suite_runner import SuiteRunner, resolve_enabled
from india_trader.upstox import INDICES, UpstoxError, UpstoxReader, load_today_master, select_atm

OUT = Path("trader/strategy_suite_live")
MARKETS = ("NIFTY", "SENSEX")
# Conservative defaults mirroring the Dhansetu-mapped client settings.
RISK = {
    "S2_supertrend_sma": RiskParams(30, 50, 4, 65, "NFO"),
    "S4_buffer_breakout": RiskParams(30, 60, 4, 65, "NFO"),
    "S5_sma_rsi": RiskParams(30, 50, 4, 65, "NFO"),
}


class LiveUpstoxProvider:
    """Adapts UpstoxReader to PaperExecutionEngine's provider interface."""

    def __init__(self, api: UpstoxReader, records, today: dt.date):
        self.api, self.records, self.today = api, records, today
        self._keys = {}   # symbol -> instrument_key, for re-quoting

    def atm(self, underlying, side, price, now):
        want = "BUY" if side == LONG else "SELL"
        try:
            c = select_atm(self.records, underlying, want, float(price), self.today)
            q = self.api.full_quote(c["instrument_key"])
        except (UpstoxError, KeyError, ValueError):
            return None
        if abs((now - q.timestamp).total_seconds()) > 20 or q.bid <= 0 or q.ask <= 0:
            return None
        self._keys[c["symbol"]] = c["instrument_key"]
        return OptionQuote(c["symbol"], q.bid, q.ask, c["exchange"])

    def quote(self, symbol, now):
        key = self._keys.get(symbol)
        if not key:
            return None
        try:
            q = self.api.full_quote(key)
        except (UpstoxError, KeyError, ValueError):
            return None
        if abs((now - q.timestamp).total_seconds()) > 20 or q.bid <= 0 or q.ask <= 0:
            return None
        return OptionQuote(symbol, q.bid, q.ask, symbol.split(":")[0])


def run():
    if os.environ.get("RUN_STRATEGY_SUITE") != "1":
        print("strategy suite disabled (set RUN_STRATEGY_SUITE=1 to enable)")
        return
    now = dt.datetime.now(IST)
    if now.weekday() > 4 or now.time() >= dt.time(14, 45):
        print("outside market-day startup")
        return
    if not os.environ.get("UPSTOX_ACCESS_TOKEN"):
        raise RuntimeError("Missing read-only Upstox token")
    api = UpstoxReader()
    records = load_today_master("trader/upstox_instruments.json", now.date())
    enabled = resolve_enabled(os.environ.get("ALGOBANI_ENABLE_STRATEGIES", "ALL"))
    engine = PaperExecutionEngine(LiveUpstoxProvider(api, records, now.date()))
    suite = SuiteRunner(engine, enabled, RISK)
    OUT.mkdir(parents=True, exist_ok=True)
    journal = OUT / (str(now.date()) + ".jsonl")
    if journal.exists():
        raise RuntimeError("Duplicate suite journal; refusing to restart")
    end = env_time("PAPER_SESSION_END", dt.time(15, 30))
    flat = env_time("PAPER_FLAT_BY", dt.time(15, 25))
    last = {}
    with journal.open("x") as f:
        f.write(json.dumps({"event": "SESSION_START", "session": "strategy_suite",
                            "market": "BOTH", "capital": 15000, "mode": "PAPER_ONLY_NO_ORDERS",
                            "enabled": enabled, "timestamp": now.isoformat()}) + "\n")
        f.flush()
        while dt.datetime.now(IST).time() < end:
            now = dt.datetime.now(IST)
            for market in MARKETS:
                try:
                    raw = api.candles(INDICES[market])
                except UpstoxError:
                    continue
                bars = sorted((b for b in raw if b.time.date() == now.date()
                               and b.time + dt.timedelta(minutes=5) <= now), key=lambda b: b.time)
                if len(bars) < 21 or last.get(market) == bars[-1].time:
                    continue
                last[market] = bars[-1].time
                suite.step(market, bars, now)
            if now.time() >= flat:
                suite.close_all(now)
                break
            time.sleep(20)
        for row in engine.audit:
            f.write(json.dumps({"event": "SUITE_AUDIT", **row}, default=str) + "\n")
        f.write(json.dumps({"event": "SESSION_SUMMARY", "session": "strategy_suite",
                            "market": "BOTH", "status": "COMPLETE",
                            "summary": {"opens": sum(1 for a in engine.audit if a["action"] == "OPEN"),
                                        "closes": sum(1 for a in engine.audit if a["action"] == "CLOSE")},
                            "session_end_ist": end.strftime("%H:%M"),
                            "timestamp": dt.datetime.now(IST).isoformat()}) + "\n")
        f.flush()


if __name__ == "__main__":
    run()
