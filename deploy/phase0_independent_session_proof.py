"""Offline-only supplementary evidence gate; never a market calendar authority.

CHG-20261122-A2-1902. No runtime wiring, data writes, or session approval.
"""
import datetime as dt
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def assess_independent_proof(record):
    """Require externally corroborated identity, coverage and terminal lineage.

    The caller MUST verify the calendar against an authoritative versioned exchange
    schedule. Claimed booleans alone cannot prove calendar membership.
    """
    if not isinstance(record, dict):
        return "BLOCKED_MALFORMED_EVIDENCE"
    if record.get("data_type") != "PAPER_SIMULATION":
        return "BLOCKED_NON_PAPER"
    if record.get("market") not in ("NIFTY", "SENSEX"):
        return "BLOCKED_MARKET_IDENTITY"
    sid, attempt = record.get("session_id"), record.get("attempt_id")
    if not isinstance(sid, str) or not sid.strip() or not isinstance(attempt, str) or not attempt.strip():
        return "BLOCKED_SESSION_IDENTITY"
    start, end = record.get("worker_started_at"), record.get("worker_ended_at")
    if not all(isinstance(x, dt.datetime) and x.tzinfo is not None for x in (start, end)):
        return "BLOCKED_WORKER_TIMESTAMPS"
    a, b = start.astimezone(IST), end.astimezone(IST)
    if b <= a or a.date() != b.date() or record.get("trading_date_ist") != a.date().isoformat():
        return "BLOCKED_DATE_LINEAGE"
    if a.weekday() >= 5:
        return "BLOCKED_WEEKEND"
    if not all(isinstance(record.get(k), str) and record[k].strip() for k in
               ("calendar_exchange", "calendar_version", "calendar_source_id")):
        return "BLOCKED_CALENDAR_PROVENANCE"
    if record.get("calendar_exchange") != "NSE" and record.get("market") == "NIFTY":
        return "BLOCKED_CALENDAR_EXCHANGE"
    if record.get("calendar_exchange") != "BSE" and record.get("market") == "SENSEX":
        return "BLOCKED_CALENDAR_EXCHANGE"
    if record.get("exchange_session_confirmed") is not True:
        return "BLOCKED_EXCHANGE_SESSION_UNVERIFIED"
    if a.time() > dt.time(9, 15) or b.time() < dt.time(15, 30):
        return "BLOCKED_INCOMPLETE_WORKER_WINDOW"
    if record.get("continuous_coverage_verified") is not True or not record.get("coverage_evidence_id"):
        return "BLOCKED_COVERAGE_LINEAGE"
    events = record.get("terminal_events")
    if not isinstance(events, list) or len(events) != 1:
        return "BLOCKED_TERMINAL_EVENT_CARDINALITY"
    event = events[0]
    if not isinstance(event, dict) or any(event.get(k) != record.get(k) for k in
                                             ("session_id", "attempt_id", "market")):
        return "BLOCKED_TERMINAL_IDENTITY"
    if event.get("lease_id") != record.get("lease_id") or not record.get("lease_id"):
        return "BLOCKED_TERMINAL_LEASE"
    if event.get("reason") != "SCHEDULED_MARKET_CLOSE":
        return "BLOCKED_TERMINAL_REASON"
    if record.get("journal_reconciled") is not True:
        return "BLOCKED_JOURNAL_RECONCILIATION"
    return "ELIGIBLE_FOR_INDEPENDENT_REVIEW"
