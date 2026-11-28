"""S11.2 — daily goal tracker (Phase 11).

Reads today's monitor feed (deploy.monitor_feed) and classifies the day against
the frozen Phase-11 target bands. Writes trader/goal_check.json (consumed by the
monitor UI) and prints a one-line human verdict. Paper only; no trading actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from deploy import monitor_feed
from india_trader import performance_targets as pt


def check(journal_dir: str = "trader/paper_upstox", session_date: str | None = None,
          capital: float = 15000.0) -> dict:
    payload = monitor_feed.build(journal_dir, session_date)
    day = payload.get("day") or {}
    net = day.get("net_pnl")
    trades = day.get("trades") or 0
    # If no session has run at all, don't classify a bogus "FLAT" from zero data.
    if payload.get("status") == "NO_SESSION":
        verdict = pt.classify_day(None)
    else:
        verdict = pt.classify_day(net, trades=trades, capital=capital)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "session_date": payload.get("session_date"),
        "session_status": payload.get("status"),
        "capital": capital,
        **verdict,
    }


def one_line(r: dict) -> str:
    v = r["verdict"]
    if v == pt.NO_DATA:
        return f"{r['session_date']}: no session data yet."
    tag = {pt.GREEN: "GREEN ✓", pt.FLAT: "FLAT ·", pt.RED: "RED ↓",
           pt.STOP_HIT: "STOP HIT ✗", pt.NO_DATA: "—"}[v]
    cadence = {"ON_TARGET": "cadence 4-7 ✓", "UNDER": "under cadence",
               "OVER": "over cadence", "NONE": "no trades"}[r["cadence"]]
    return (f"{r['session_date']}: {tag} net ₹{r['net_pnl']:+.0f} "
            f"({r['trades']} trades, {cadence}); band expected ₹{r['band']['expected']:+.0f}, "
            f"stop ₹{r['band']['hard_stop']:+.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-dir", default="trader/paper_upstox")
    ap.add_argument("--out", default="trader/goal_check.json")
    ap.add_argument("--date", default=None)
    ap.add_argument("--capital", type=float, default=15000.0)
    a = ap.parse_args()
    r = check(a.journal_dir, a.date, capital=a.capital)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(r, indent=2))
    print(one_line(r))


if __name__ == "__main__":
    main()
