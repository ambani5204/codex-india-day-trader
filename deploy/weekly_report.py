"""S11.4 — weekly reconciliation report (Phase 11).

Sums the week's closed-trade P&L across all paper journals, classifies the week
against the frozen weekly band, and lists a per-strategy breakdown. Pure
aggregation of real journal data — no invented numbers. Intended to run Friday
evenings; safe on empty data (NO_SESSION week).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from pathlib import Path
from typing import List

from india_trader import performance_targets as pt


CLOSED_EVENTS = ("PAPER_TRADE_CLOSED", "OPTION_PAPER_CLOSED")
PNL_FIELDS = ("net_pnl_inr", "net_pnl", "Total", "total")


def _first(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _week_dates(end: dt.date) -> List[dt.date]:
    """The Monday..Friday on-or-before `end` (week ending that Friday)."""
    # Rewind to the Friday of this week.
    delta_to_fri = (end.weekday() - 4) % 7
    fri = end - dt.timedelta(days=delta_to_fri)
    return [fri - dt.timedelta(days=i) for i in range(4, -1, -1)]  # Mon..Fri


def generate(journal_dir: str, week_ending: dt.date | None = None,
             capital: float = 15000.0) -> dict:
    d = Path(journal_dir)
    end = week_ending or dt.date.today()
    dates = _week_dates(end)
    daily_pnls: List[float] = []
    by_strategy: dict = collections.Counter()
    per_day = []
    for day in dates:
        day_s = day.isoformat()
        day_net = 0.0
        day_trades = 0
        session_present = False
        if d.exists():
            for jf in d.glob(f"{day_s}*.jsonl"):
                session_present = True
                for line in jf.read_text(encoding="utf-8").splitlines():
                    try:
                        e = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(e, dict):
                        continue
                    if e.get("event") in CLOSED_EVENTS:
                        p = _first(e, PNL_FIELDS)
                        if p is not None:
                            try:
                                p = float(p)
                            except (TypeError, ValueError):
                                continue
                            day_net += p
                            day_trades += 1
                            by_strategy[str(e.get("strategy", "legacy"))] += p
        daily_pnls.append(day_net if session_present else None)
        per_day.append({
            "date": day_s, "sessions_found": session_present,
            "net_pnl": round(day_net, 2), "trades": day_trades,
            "verdict": (pt.classify_day(day_net, trades=day_trades)["verdict"]
                        if session_present else pt.NO_DATA),
        })
    week = pt.classify_week([x for x in daily_pnls if x is not None], capital=capital)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "week_ending": dates[-1].isoformat(),
        "capital": capital,
        "week": week,
        "per_day": per_day,
        "per_strategy": {k: round(v, 2) for k, v in sorted(by_strategy.items())},
    }


def one_line(r: dict) -> str:
    w = r["week"]
    sess = w["sessions"]
    if sess == 0:
        return f"Week ending {r['week_ending']}: no sessions found."
    tag = {pt.GREEN: "GREEN ✓", pt.FLAT: "FLAT ·", pt.RED: "RED ↓",
           pt.STOP_HIT: "STOP HIT ✗", pt.NO_DATA: "—"}.get(w["verdict"], w["verdict"])
    return (f"Week ending {r['week_ending']}: {tag} "
            f"net ₹{w['net_pnl']:+.0f} over {sess} session(s); "
            f"band expected ₹{w['band']['expected']:+.0f}, "
            f"stop ₹{w['band']['hard_stop']:+.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-dir", default="trader/paper_upstox")
    ap.add_argument("--out", default="trader/weekly_report.json")
    ap.add_argument("--week-ending", default=None, help="YYYY-MM-DD (default today)")
    ap.add_argument("--capital", type=float, default=15000.0)
    a = ap.parse_args()
    end = dt.date.fromisoformat(a.week_ending) if a.week_ending else None
    r = generate(a.journal_dir, end, capital=a.capital)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(r, indent=2))
    print(one_line(r))


if __name__ == "__main__":
    main()
