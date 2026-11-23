"""CHG-20261123-A2-0658: offline-only terminal consensus gate.

Never grants session acceptance. Independent exchange-calendar provenance,
producer identity and journal reconciliation are still required.
"""
import datetime as dt
from zoneinfo import ZoneInfo
from deploy.phase0_scheduled_close_clock_gate import assess_scheduled_close

IST = ZoneInfo("Asia/Kolkata")


def assess_terminal_consensus(record):
    baseline = assess_scheduled_close(record)
    if baseline != "ELIGIBLE_FOR_EXTERNAL_CALENDAR_AND_PROVENANCE_REVIEW":
        return baseline
    events = record.get("terminal_events")
    if not isinstance(events, list) or len(events) != 1:
        return "BLOCKED_TERMINAL_EVENT_CARDINALITY"
    event = events[0]
    if not isinstance(event, dict):
        return "BLOCKED_TERMINAL_EVENT_TYPE"
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        return "BLOCKED_TERMINAL_EVENT_ID"
    timestamp = event.get("timestamp")
    start = record.get("worker_started_at")
    end = record.get("worker_ended_at")
    if any(not isinstance(x, dt.datetime) or x.tzinfo is None or x.utcoffset() is None
           for x in (timestamp, start, end)):
        return "BLOCKED_TERMINAL_TIMESTAMP"
    start_ist, end_ist, terminal_ist = (x.astimezone(IST) for x in (start, end, timestamp))
    if start_ist.date() != end_ist.date() or terminal_ist.date() != start_ist.date():
        return "BLOCKED_CROSS_DATE_TERMINAL"
    if terminal_ist != end_ist:
        return "BLOCKED_TERMINAL_END_MISMATCH"
    if event.get("reason") != "SCHEDULED_MARKET_CLOSE":
        return "BLOCKED_TERMINAL_REASON"
    return "ELIGIBLE_FOR_EXTERNAL_CALENDAR_AND_PROVENANCE_REVIEW"
