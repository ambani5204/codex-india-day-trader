"""Option-P&L backtest over REAL historical index candles (strategy-spec-dhansetu-v1).

Fetches real Upstox 5-min index candles (via historical_backtest.load_historical_index),
runs each strategy detector per session, and models the ATM option P&L with
Black-Scholes greeks along the real index path, through the paper execution
engine (SL/TP in premium points, decay, real round-trip fees, EOD).

HONEST SCOPE: the index path is REAL; option premiums are MODELLED (Black-Scholes
at an assumed constant IV, no real bid/ask depth or IV surface). So net P&L /
drawdown are MODEL ESTIMATES grounded in real underlying history — approximate,
sensitive to the IV assumption, and NOT a broker-verified result. Reported as
such. Real fills come only from forward paper.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from ..core import orb_signal
from ..historical_backtest import load_historical_index
from ..options_pricing import price
from ..upstox import UpstoxReader
from .. import ema9_ema15_live_rules as ema
from . import buffer_breakout, sma_rsi, supertrend_sma
from .backtest import metrics_from_closes, run_session
from .common import LONG, OPEN, SHORT, SignalEvent
from .paper_exec import OptionQuote, RiskParams

R = 0.065  # annual risk-free rate
STEP = {"NIFTY": 50, "SENSEX": 100}
EXCH = {"NIFTY": "NFO", "SENSEX": "BFO"}
# config risk defaults (SL, TP premium points, lot qty)
RISK = {"NIFTY": RiskParams(30, 50, 5, 65, "NFO"),
        "SENSEX": RiskParams(30, 70, 4, 20, "BFO")}


class BSProvider:
    """Models ATM option premiums via Black-Scholes along the real index path."""

    def __init__(self, market, iv, dte_days, spread_pct=0.5):
        self.market = market
        self.iv = iv
        self.dte = dte_days
        self.spread = spread_pct / 100.0
        self.step = STEP[market]
        self.ex = EXCH[market]
        self.spot = None
        self.now = None
        self.opened = {}

    def set(self, spot, now):
        self.spot = spot
        self.now = now

    def atm(self, underlying, side, signal_price, now):
        call = side == LONG
        strike = round(signal_price / self.step) * self.step
        prem = price(signal_price, strike, self.dte / 365.0, R, self.iv, call)
        if prem < 1.0:
            return None
        sym = f"{underlying}-{strike}-{'CE' if call else 'PE'}-{now.isoformat()}"
        self.opened[sym] = (strike, call, now)
        return OptionQuote(sym, bid=prem * (1 - self.spread), ask=prem * (1 + self.spread),
                           exchange=self.ex, delta=0.5)

    def quote(self, sym, now):
        strike, call, opened = self.opened[sym]
        elapsed_days = (now - opened).total_seconds() / 86400.0
        t = max(self.dte - elapsed_days, 1e-6) / 365.0
        prem = max(price(self.spot, strike, t, R, self.iv, call), 0.05)
        return OptionQuote(sym, bid=prem, ask=prem * (1 + self.spread), exchange=self.ex)


def _orb_events(bars, market):
    day = bars[0].time.date()
    s = orb_signal(bars, trading_day=day)
    if s.get("status") != "TRIGGERED":
        return []
    side = LONG if s["side"] == "BUY" else SHORT
    return [SignalEvent(s["trigger_time"], OPEN, side, s["entry_price"], "ORB", "ORB")]


def _ema_events(bars, market):
    out = []
    for i in range(21, len(bars) + 1):
        try:
            sig = ema.detect(bars[:i])
        except Exception:
            sig = None
        if sig is not None:
            side = LONG if sig.side == 1 else SHORT
            out.append(SignalEvent(bars[i - 1].time.isoformat(), OPEN, side, bars[i - 1].close, "EMA", "EMA9_15"))
            break  # one entry per session
    return out


DETECTORS = {
    "S2_supertrend_sma": lambda bars, m: supertrend_sma.signals(bars),
    "S4_buffer_breakout": lambda bars, m: buffer_breakout.signals(bars),
    "S5_sma_rsi": lambda bars, m: sma_rsi.signals(bars),
    "ORB": _orb_events,
    "EMA9_15": _ema_events,
}


def run(market: str, days: int, iv: float, dte_days: float = 3.0) -> dict:
    reader = UpstoxReader()
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    bars = load_historical_index(reader, market, start, end, "trader/backtest_cache")
    by_day = {}
    for b in bars:
        by_day.setdefault(b.time.date(), []).append(b)
    sessions = sorted(by_day)
    results = {}
    for name, detect in DETECTORS.items():
        risk = RISK[market]
        all_closed = []
        for d in sessions:
            sbars = sorted(by_day[d], key=lambda x: x.time)
            if len(sbars) < 22:
                continue
            try:
                evs = detect(sbars, market)
            except Exception:
                evs = []
            if not evs:
                continue
            prov = BSProvider(market, iv, dte_days)
            evs = [SignalEvent(e.bar_time, e.action, e.side, e.price, e.reason, name) for e in evs]
            all_closed += run_session(evs, sbars, prov, market, risk)
        results[name] = metrics_from_closes(all_closed)
    return {"market": market, "days": days, "sessions": len(sessions),
            "iv_assumption": iv, "dte_days": dte_days,
            "model_note": "REAL index candles; MODELLED Black-Scholes option premiums at constant IV. "
                          "P&L is an approximate model estimate, sensitive to IV, not broker-verified.",
            "strategies": results}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--market", choices=["NIFTY", "SENSEX"], required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--iv", type=float, default=0.15)
    p.add_argument("--dte-days", type=float, default=3.0)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    out = run(a.market, a.days, a.iv, a.dte_days)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out["strategies"], indent=2))
    print(f"\\n{out['model_note']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
