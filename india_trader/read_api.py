"""Versioned READ-ONLY API over paper-session data (Phase 7).

A stable, versioned facade the monitor (and any external reader) consumes. It
only ever READS journals — it never fetches quotes, writes files, or places
orders. The envelope carries api_version so the client can guard on it; the
payload is the monitor contract (see deploy.monitor_feed).

Breaking the payload shape requires bumping API_VERSION; additive fields do not.
"""
from __future__ import annotations

from typing import Optional

from deploy import monitor_feed

API_VERSION = "1"

# The payload keys guaranteed by API_VERSION 1. Clients may rely on these.
CONTRACT_V1 = ("session_date", "status", "source", "day", "strategies", "signals", "history")
STATUSES = ("NO_SESSION", "RUNNING", "COMPLETE")


def get(journal_dir: str = "trader/paper_upstox", session_date: Optional[str] = None) -> dict:
    """Return the versioned read-only snapshot. Pure read; no side effects."""
    payload = monitor_feed.build(journal_dir, session_date)
    return {"api_version": API_VERSION, **payload}


def validate(envelope: dict) -> list:
    """Return a list of contract violations (empty = valid)."""
    errors = []
    if envelope.get("api_version") != API_VERSION:
        errors.append(f"api_version must be {API_VERSION!r}")
    for key in CONTRACT_V1:
        if key not in envelope:
            errors.append(f"missing required field: {key}")
    if envelope.get("status") not in STATUSES:
        errors.append(f"status must be one of {STATUSES}")
    day = envelope.get("day", {})
    if not isinstance(day, dict) or not {"net_pnl", "trades", "win_rate"} <= set(day):
        errors.append("day must have net_pnl, trades, win_rate")
    if not isinstance(envelope.get("strategies"), list):
        errors.append("strategies must be a list")
    return errors


# Narrow read-only accessors (so a caller need not know the payload shape).
def status(journal_dir: str = "trader/paper_upstox") -> str:
    return get(journal_dir)["status"]


def day_pnl(journal_dir: str = "trader/paper_upstox") -> float:
    return get(journal_dir)["day"]["net_pnl"]


def strategy_pnl(journal_dir: str = "trader/paper_upstox") -> dict:
    return {s["name"]: s["pnl"] for s in get(journal_dir)["strategies"]}
