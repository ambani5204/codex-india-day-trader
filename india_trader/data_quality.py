"""Candle data-quality / coverage checks (Phase 3).

Validates fetched 5-minute index candles per session: expected bar count,
missing bars, duplicates, out-of-order, and bars outside market hours. Produces
a coverage report so a session with incomplete data is flagged rather than
silently backtested or traded on.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Dict, List, Sequence

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SESSION_OPEN = dt.time(9, 15)
SESSION_CLOSE = dt.time(15, 30)
BAR_MINUTES = 5
# 09:15..15:25 inclusive start stamps = (15:30-09:15)/5 = 75 bars
EXPECTED_BARS = 75


def expected_stamps(day: dt.date) -> List[dt.time]:
    out = []
    t = dt.datetime.combine(day, SESSION_OPEN, IST)
    end = dt.datetime.combine(day, SESSION_CLOSE, IST)
    while t < end:
        out.append(t.timetz().replace(tzinfo=None))
        t += dt.timedelta(minutes=BAR_MINUTES)
    return out


def session_coverage(bars: Sequence, day: dt.date) -> dict:
    """Coverage metrics for one session's bars."""
    stamps = [b.time.astimezone(IST) for b in bars if b.time.astimezone(IST).date() == day]
    times = [s.timetz().replace(tzinfo=None) for s in stamps]
    counts = Counter(times)
    expected = expected_stamps(day)
    present = set(times)
    missing = [t for t in expected if t not in present]
    duplicates = sorted(t.isoformat() for t, c in counts.items() if c > 1)
    outside = sorted(t.isoformat() for t in times if t < SESSION_OPEN or t >= SESSION_CLOSE)
    ordered = times == sorted(times)
    have = len([t for t in times if SESSION_OPEN <= t < SESSION_CLOSE])
    return {
        "date": day.isoformat(),
        "expected_bars": EXPECTED_BARS,
        "present_in_hours": have,
        "coverage_pct": round(100 * have / EXPECTED_BARS, 1),
        "missing_bars": len(missing),
        "duplicates": duplicates,
        "out_of_hours": outside,
        "ordered": ordered,
        "complete": len(missing) == 0 and not duplicates and not outside and ordered,
    }


def coverage_report(bars: Sequence) -> dict:
    """Aggregate coverage across all sessions present in bars."""
    by_day: Dict[dt.date, list] = {}
    for b in bars:
        by_day.setdefault(b.time.astimezone(IST).date(), []).append(b)
    sessions = {d.isoformat(): session_coverage(bs, d) for d, bs in sorted(by_day.items())}
    complete = sum(1 for s in sessions.values() if s["complete"])
    return {
        "sessions": len(sessions),
        "complete_sessions": complete,
        "incomplete_sessions": len(sessions) - complete,
        "per_session": sessions,
    }
