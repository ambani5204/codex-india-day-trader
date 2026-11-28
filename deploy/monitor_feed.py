"""Build the Algobani monitor's data.json from paper-session journals.

Reads the day's *.jsonl journals (any sidecar/ledger shape) and emits the JSON
the monitor UI consumes. Tolerant: unknown events are ignored, and a missing
P&L/field never raises. PAPER only — reports what the journals contain, never
invents trades or prices.

Monitor JSON schema (v1):
{
  "generated_at": iso, "session_date": "YYYY-MM-DD",
  "status": "RUNNING|COMPLETE|NO_SESSION",
  "source": "LIVE|SAMPLE",
  "day": {"net_pnl": float, "trades": int, "win_rate": "NN%"},
  "strategies": [{"name","pnl","trades","win"}],
  "signals": [["time","symbol","strike","type","px"]],
  "history": [["time","strategy","symbol","in","out","exit","pnl"]]
}
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Iterable

CLOSED_EVENTS = {"PAPER_TRADE_CLOSED", "OPTION_PAPER_CLOSED"}
PNL_FIELDS = ("net_pnl_inr", "net_pnl", "Total", "total")
SIGNAL_EVENTS = {"INDEX_SIGNAL"}


def _first(d: dict, keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _pnl(d: dict):
    v = _first(d, PNL_FIELDS)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iter_events(paths: Iterable[Path]):
    for p in paths:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                e = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(e, dict) and e.get("event"):
                yield e


def build(journal_dir: str, session_date: str | None = None) -> dict:
    d = Path(journal_dir)
    paths = sorted(d.glob("*.jsonl")) if d.exists() else []
    events = list(_iter_events(paths))
    session_date = session_date or (dt.date.today().isoformat())

    closed = []          # (time, strategy, symbol, entry, exit, reason, pnl)
    signals = []         # [time, symbol, strike, type, px]
    by_strat = {}        # strategy -> [pnl,...]
    for e in events:
        ev = e.get("event")
        if ev == "SUITE_AUDIT" and e.get("action") == "CLOSE":
            p = _pnl(e)
            strat = str(e.get("strategy", "?"))
            closed.append((e.get("ts", ""), strat, e.get("symbol", ""),
                           e.get("entry_premium", ""), e.get("exit_premium", ""),
                           e.get("exit_type", e.get("reason", "")), p))
            by_strat.setdefault(strat, []).append(p)
        elif ev in CLOSED_EVENTS:
            p = _pnl(e)
            strat = str(_first(e, ("strategy",), "legacy"))
            closed.append((_short_time(_first(e, ("time", "timestamp"), "")), strat,
                           e.get("symbol", ""), _first(e, ("entry_price",), ""),
                           _first(e, ("exit_price",), ""), e.get("reason", ""), p))
            by_strat.setdefault(strat, []).append(p)
        elif ev in SIGNAL_EVENTS:
            signals.append([_short_time(_first(e, ("time", "timestamp"), "")),
                            e.get("market", ""), str(e.get("strike", e.get("direction", ""))),
                            e.get("direction", e.get("ordertype", "")),
                            str(_first(e, ("signal_close", "signal_price", "signalprice"), ""))])

    pnls = [p for _, _, _, _, _, _, p in closed if p is not None]
    wins = [p for p in pnls if p > 0]
    status = "NO_SESSION"
    if any(e.get("event") == "SESSION_SUMMARY" for e in events):
        status = "COMPLETE"
    elif events:
        status = "RUNNING"

    strategies = []
    for strat, ps in sorted(by_strat.items()):
        good = [x for x in ps if x is not None]
        w = [x for x in good if x > 0]
        strategies.append({
            "name": strat,
            "pnl": round(sum(good), 2),
            "trades": len(ps),
            "win": f"{round(100*len(w)/len(good))}%" if good else "—",
        })

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "session_date": session_date,
        "status": status,
        "source": "LIVE",
        "day": {
            "net_pnl": round(sum(pnls), 2),
            "trades": len(closed),
            "win_rate": f"{round(100*len(wins)/len(pnls))}%" if pnls else "—",
        },
        "strategies": strategies,
        "signals": signals[-25:],
        "history": [[t, s, sym, i, o, r, (round(p, 2) if p is not None else None)]
                    for (t, s, sym, i, o, r, p) in closed[-40:]],
    }


def _short_time(ts: str) -> str:
    try:
        return dt.datetime.fromisoformat(str(ts)).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return str(ts)[:8]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-dir", default="trader/paper_upstox")
    ap.add_argument("--out", default="trader/monitor_data.json")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    data = build(a.journal_dir, a.date)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=2))
    print(f"wrote {a.out}: status={data['status']} trades={data['day']['trades']} "
          f"net={data['day']['net_pnl']}")


if __name__ == "__main__":
    main()
