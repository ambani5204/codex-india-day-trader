"""Supplemental offline-only negative evidence checks. CHG-20261123-A2-0157.

No runtime wiring. Caller assertions are not independent calendar authority.
"""
import datetime as dt
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def assess_lineage_evidence(record):
    """Fail closed on malformed heartbeat and terminal lineage; never approve a session."""
    if not isinstance(record, dict):
        return "BLOCKED_MALFORMED"
    for key in ("session_id", "attempt_id", "market", "lease_id", "coverage_evidence_id"):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            return "BLOCKED_IDENTITY_TYPE"
    if record["market"] not in ("NIFTY", "SENSEX"):
        return "BLOCKED_MARKET"
    start, end = record.get("worker_started_at"), record.get("worker_ended_at")
    if not all(isinstance(v, dt.datetime) and v.tzinfo is not None and v.utcoffset() is not None for v in (start, end)):
        return "BLOCKED_TIMEZONE"
    if start >= end or start.astimezone(IST).date() != end.astimezone(IST).date():
        return "BLOCKED_WORKER_INTERVAL"
    beats = record.get("heartbeats")
    if not isinstance(beats, list) or len(beats) < 2:
        return "BLOCKED_HEARTBEATS"
    previous = None
    for beat in beats:
        if not isinstance(beat, dict):
            return "BLOCKED_HEARTBEAT_IDENTITY"
        if any(beat.get(k) != record[k] for k in ("session_id", "attempt_id", "market", "lease_id")):
            return "BLOCKED_HEARTBEAT_IDENTITY"
        stamp = beat.get("timestamp")
        if not isinstance(stamp, dt.datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            return "BLOCKED_HEARTBEAT_TIMESTAMP"
        if stamp < start or stamp > end or (previous is not None and (stamp - previous).total_seconds() <= 0):
            return "BLOCKED_HEARTBEAT_ORDER"
        if previous is not None and (stamp - previous).total_seconds() > 120:
            return "BLOCKED_HEARTBEAT_GAP"
        previous = stamp
    if (beats[0]["timestamp"] - start).total_seconds() > 120 or (end - previous).total_seconds() > 120:
        return "BLOCKED_HEARTBEAT_EDGE"
    events = record.get("terminal_events")
    if not isinstance(events, list) or len(events) != 1 or not isinstance(events[0], dict):
        return "BLOCKED_TERMINAL_CARDINALITY"
    event = events[0]
    if any(event.get(k) != record[k] for k in ("session_id", "attempt_id", "market", "lease_id")):
        return "BLOCKED_TERMINAL_IDENTITY"
    if not isinstance(event.get("event_id"), str) or not event["event_id"].strip():
        return "BLOCKED_TERMINAL_EVENT_ID"
    stamp = event.get("timestamp")
    if not isinstance(stamp, dt.datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        return "BLOCKED_TERMINAL_TIMESTAMP"
    if stamp < previous or stamp > end or (end - stamp).total_seconds() > 120:
        return "BLOCKED_TERMINAL_TIME_LINK"
    if event.get("reason") != "SCHEDULED_MARKET_CLOSE":
        return "BLOCKED_TERMINAL_REASON"
    return "ELIGIBLE_FOR_EXTERNAL_CORROBORATION"
