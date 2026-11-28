"""ALGOBANI event-ledger contract + validator (Phase 2: contracts, event ledger, schema).

The per-session journals are the event ledger: append-only JSONL, one event per
line. This module is the machine-readable CONTRACT for that ledger — the required
fields per event type and the ordering invariants — plus a fail-closed validator
used in CI and by reconciliation. It does not emit events; it validates them.

Versioned so the contract can evolve without silently accepting malformed ledgers.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, Iterable, List

SCHEMA_VERSION = "1.0"

# Every event must carry these.
UNIVERSAL = ("event", "timestamp")

# Event-specific required fields (beyond UNIVERSAL). Only invariant fields are
# required; optional/diagnostic fields are allowed and ignored.
EVENT_REQUIRED: Dict[str, tuple] = {
    "SESSION_START": ("session", "market", "capital", "mode"),
    "SESSION_SUMMARY": ("session", "market", "status", "summary"),
    "SESSION_PAUSED": ("session", "market"),            # two-job split handoff marker
    "INDEX_SIGNAL": ("market", "side", "strategy"),
    "RISK_PLAN": ("market", "risk_budget"),
    "STRATEGY_DECISION": ("market", "strategy", "trade_structure"),
    "STRUCTURE_REJECTED": ("market", "reason"),
    "SIGNAL_REJECTED": ("market",),
    "OPTION_PAPER_OPEN": ("market", "symbol"),
    "OPTION_PAPER_CLOSED": ("market", "symbol"),
    "PAPER_TRADE_CLOSED": ("market",),
    "UNRESOLVED_POSITION": ("market",),
}

# A ledger must end in one of these terminal events (fail closed otherwise).
TERMINAL_EVENTS = ("SESSION_SUMMARY", "UNRESOLVED_POSITION", "SESSION_PAUSED")


class LedgerError(ValueError):
    pass


def _parse_ts(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return stamp


def validate_event(event: dict) -> List[str]:
    """Return a list of contract violations for one event ([] = valid)."""
    errors: List[str] = []
    if not isinstance(event, dict):
        return ["event is not an object"]
    for f in UNIVERSAL:
        if f not in event:
            errors.append(f"missing universal field '{f}'")
    kind = event.get("event")
    if "timestamp" in event:
        try:
            _parse_ts(event["timestamp"])
        except ValueError as exc:
            errors.append(f"bad timestamp: {exc}")
    if kind in EVENT_REQUIRED:
        for f in EVENT_REQUIRED[kind]:
            if f not in event:
                errors.append(f"{kind}: missing required field '{f}'")
    return errors


def validate_ledger(events: Iterable[dict], require_terminal: bool = True) -> List[str]:
    """Validate a whole session ledger. Returns [] if it satisfies the contract."""
    events = list(events)
    errors: List[str] = []
    if not events:
        return ["empty ledger"]
    if events[0].get("event") != "SESSION_START":
        errors.append("first event must be SESSION_START")
    # per-event
    for i, e in enumerate(events):
        for err in validate_event(e):
            errors.append(f"[{i}] {err}")
    # monotonic timestamps
    prev = None
    for i, e in enumerate(events):
        try:
            cur = _parse_ts(e["timestamp"])
        except (KeyError, ValueError):
            continue
        if prev is not None and cur < prev:
            errors.append(f"[{i}] timestamp goes backwards")
        prev = cur
    # terminal
    if require_terminal and events[-1].get("event") not in TERMINAL_EVENTS:
        errors.append(f"ledger does not end in a terminal event {TERMINAL_EVENTS}; "
                      f"ends in {events[-1].get('event')!r}")
    return errors


def load_jsonl(path) -> List[dict]:
    import json
    from pathlib import Path
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
