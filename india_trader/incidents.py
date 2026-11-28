"""Durable incident log (Phase 6).

Append-only JSONL record of operational incidents so a crash, a stale-lease
takeover, or an unresolved-position-on-recovery is never silent. Each line is
one incident; the file is only ever appended to, so history is preserved (the
mandate: preserve all records). No raw quotes or trade detail — operational
metadata only, safe to keep.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from india_trader.core import IST

# Known incident kinds (free-form allowed, but these are the expected ones).
STALE_LEASE_TAKEOVER = "STALE_LEASE_TAKEOVER"
DOUBLE_WORKER_BLOCKED = "DOUBLE_WORKER_BLOCKED"
CRASH_NO_TERMINAL = "CRASH_NO_TERMINAL"
UNRESOLVED_ON_RECOVERY = "UNRESOLVED_ON_RECOVERY"


def record(path: Path, kind: str, *, market: str = "", day: str = "",
           holder: str = "", detail: str = "",
           now: Optional[dt.datetime] = None) -> dict:
    now = now or dt.datetime.now(IST)
    entry = {
        "timestamp": now.isoformat(),
        "kind": kind,
        "market": market,
        "day": day,
        "holder": holder,
        "detail": detail,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_all(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return out
