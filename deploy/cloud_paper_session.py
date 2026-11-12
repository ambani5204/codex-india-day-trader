"""Cloud CE/PE paper session with public-safe aggregate diagnostics only.

Raw quotes/journals stay on the ephemeral runner and are NEVER uploaded.
GitHub Actions artifacts in a public repository must be treated as public.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

from india_trader.core import IST
from india_trader.schedule import market_for_day

ROOT = Path(__file__).resolve().parents[1]
JOURNALS = ROOT / "trader" / "paper_upstox"
REPORT = ROOT / "trader" / "cloud_paper_summary.json"


def summarize(day: str, market: str, worker_exit: int, startup: str) -> dict:
    """Whitelist aggregate fields; never expose quotes, strikes or API responses."""
    counts = collections.Counter()
    by_strategy = collections.Counter()
    exit_reasons = collections.Counter()
    closed = 0
    unresolved = 0
    sessions = 0
    for path in sorted(JOURNALS.glob(f"{day}_{market}_*.jsonl")):
        sessions += 1
        events = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(event, dict):
                    events.append(event)
        if not any(e.get("event") == "SESSION_SUMMARY" for e in events):
            unresolved += 1
        for e in events:
            kind = e.get("event")
            if kind in ("INDEX_SIGNAL", "SIGNAL_REJECTED", "STRUCTURE_REJECTED",
                        "MARKET_DATA_ERROR", "UNRESOLVED_POSITION",
                        "PAPER_TRADE_CLOSED", "ENTRY_REJECTED", "ENTRY_BLOCKED"):
                counts[kind] += 1
            if kind == "INDEX_SIGNAL":
                strategy = str(e.get("strategy", "UNKNOWN"))
                if strategy in ("OPENING_RANGE_BREAKOUT", "OPENING_RANGE_FAKEOUT",
                                "OPENING_RANGE_TRAP", "EMA_8_21_CROSS",
                                "MEAN_REVERSION"):
                    by_strategy[strategy] += 1
            if kind == "UNRESOLVED_POSITION":
                unresolved += 1
            if kind == "PAPER_TRADE_CLOSED":
                closed += 1
                reason = str(e.get("reason") or "")
                if reason in ("STOP", "STOP_LOSS", "TARGET", "TARGET_HIT",
                              "INDEX_STOP", "TIME_EXIT", "FLAT_BY",
                              "EOD", "TRAILING_STOP"):
                    exit_reasons[reason] += 1
                else:
                    exit_reasons["OTHER"] += 1
    return {
        "date_ist": day, "market": market,
        "mode": "READ_ONLY_SIMULATED_OPTIONS_NOT_EXCHANGE_FILLS",
        "status": "FAILED_OR_INCOMPLETE" if worker_exit or unresolved else (
            "NO_SESSION" if not sessions else "COMPLETE"),
        "startup": startup, "worker_exit_code": worker_exit,
        "sessions": sessions, "closed_trades": closed,
        "event_counts": dict(sorted(counts.items())),
        "signal_counts_by_strategy": dict(sorted(by_strategy.items())),
        "exit_reason_counts": dict(sorted(exit_reasons.items())),
        "unresolved_events_or_sessions": unresolved,
        "data_warning": "Public aggregate only. No raw quotes or individual trades stored. "
                        "API errors and missed sessions require private log review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["AUTO", "NIFTY", "SENSEX"], default="AUTO")
    args = parser.parse_args()
    now = dt.datetime.now(IST)
    market = market_for_day(now.date()) if args.market == "AUTO" else args.market
    day = now.date().isoformat()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "trader" / "config.json"
    config = json.loads((ROOT / "trader" / "config.example.json").read_text())
    config.update(paper=True, allow_derivatives=True, allow_live_orders=False)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    os.chmod(config_path, 0o600)
    startup = "READY"
    code = 1
    if not market or now.weekday() >= 5:
        startup = "NON_TRADING_WEEKDAY"
    elif not (dt.time(9, 15) <= now.time() < dt.time(15, 10)):
        startup = "START_OUTSIDE_ALLOWED_WINDOW"
    elif not os.environ.get("UPSTOX_ACCESS_TOKEN"):
        startup = "MISSING_UPSTOX_TOKEN"
    else:
        sync = subprocess.run([sys.executable, "tools/india.py", "upstox-sync"],
                              cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=100)
        if sync.returncode:
            startup = "INSTRUMENT_SYNC_FAILED"
        else:
            worker = subprocess.run(
                [sys.executable, "tools/india.py", "paper-advanced",
                 "--market", market, "--poll-seconds", "30",
                 "--cooldown-minutes", "15"],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=21300)
            code = worker.returncode
    result = summarize(day, market or "NONE", code, startup)
    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
