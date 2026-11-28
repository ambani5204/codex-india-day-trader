"""NSE/BSE trading calendar (Phase 3). Fills the gap the rest of the code flags.

is_trading_day() = weekday AND not a listed exchange holiday. The holiday list
(config/nse_holidays.json) is PARTIAL (fixed-date national holidays only); the
variable lunar holidays must be completed from the official NSE circular. This
is deliberately FAIL-SAFE: a date not in the list is treated as a trading day,
and real market data then confirms it — so a missing holiday causes at most a
harmless empty session, never a wrong trade.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "config" / "nse_holidays.json"
_cache = None


def _load():
    global _cache
    if _cache is None:
        data = json.loads(_PATH.read_text())
        holidays = {}
        for year, items in data.get("holidays", {}).items():
            for h in items:
                holidays[dt.date.fromisoformat(h["date"])] = h["name"]
        _cache = holidays
    return _cache


def is_holiday(day: dt.date) -> bool:
    return day in _load()


def holiday_name(day: dt.date):
    return _load().get(day)


def is_trading_day(day: dt.date) -> bool:
    """Weekday and not a LISTED holiday. Fail-safe for unlisted dates."""
    return day.weekday() < 5 and not is_holiday(day)


def session_bounds(day: dt.date):
    """Returns (open, close) datetimes in IST for a normal session, or None."""
    if not is_trading_day(day):
        return None
    IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return (dt.datetime.combine(day, dt.time(9, 15), IST),
            dt.datetime.combine(day, dt.time(15, 30), IST))


def trading_days(start: dt.date, end: dt.date):
    d = start
    out = []
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out
