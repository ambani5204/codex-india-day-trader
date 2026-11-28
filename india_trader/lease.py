"""Durable single-writer session lease (Phase 6).

Only one worker may own a (market, day) paper session at a time. The lease is a
small JSON file written atomically (temp + os.replace). A second worker that
finds a LIVE lease held by someone else refuses; it may take over only a lease
whose heartbeat has gone stale (crashed holder), and a takeover is surfaced as
an incident by the caller. This is the durable half of the gate's "do NOT retry
until durable recovery is proven" rule.

No network, no broker, no live orders — pure local-file coordination.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple

from india_trader.core import IST


@dataclass
class Lease:
    market: str
    day: str
    holder: str          # e.g. "<workflow>#<run_id>"
    token: str           # unique per acquisition; required to renew/release
    acquired_ts: str
    heartbeat_ts: str
    lease_seconds: int

    def is_expired(self, now: dt.datetime) -> bool:
        hb = dt.datetime.fromisoformat(self.heartbeat_ts)
        return (now - hb).total_seconds() > self.lease_seconds


def _read(path: Path) -> Optional[Lease]:
    if not path.exists():
        return None
    try:
        return Lease(**json.loads(path.read_text()))
    except (ValueError, TypeError):
        return None


def _write_atomic(path: Path, lease: Lease) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(asdict(lease), sort_keys=True))
    os.replace(tmp, path)  # atomic on POSIX


def acquire(path: Path, market: str, day: str, holder: str,
            now: Optional[dt.datetime] = None, lease_seconds: int = 600
            ) -> Tuple[bool, Lease, bool]:
    """Try to acquire/renew the lease.

    Returns (granted, lease, took_over_stale). granted=False means a live lease
    is held by another holder (caller must NOT run). took_over_stale=True means
    an expired lease was seized (caller should record an incident).
    """
    now = now or dt.datetime.now(IST)
    cur = _read(path)
    if cur is not None and not cur.is_expired(now):
        if cur.holder == holder:
            renewed = Lease(market, day, holder, cur.token,
                            cur.acquired_ts, now.isoformat(), lease_seconds)
            _write_atomic(path, renewed)
            return True, renewed, False
        return False, cur, False
    took_over = cur is not None and cur.is_expired(now)
    fresh = Lease(market, day, holder, uuid.uuid4().hex,
                  now.isoformat(), now.isoformat(), lease_seconds)
    _write_atomic(path, fresh)
    return True, fresh, took_over


def renew(path: Path, token: str, now: Optional[dt.datetime] = None) -> bool:
    now = now or dt.datetime.now(IST)
    cur = _read(path)
    if cur is None or cur.token != token:
        return False
    _write_atomic(path, Lease(cur.market, cur.day, cur.holder, cur.token,
                              cur.acquired_ts, now.isoformat(), cur.lease_seconds))
    return True


def release(path: Path, token: str) -> bool:
    cur = _read(path)
    if cur is None or cur.token != token:
        return False
    path.unlink(missing_ok=True)
    return True
