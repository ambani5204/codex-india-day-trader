"""Offline supplemental scheduled-close clock gate; CHG-20261123-A2-0400.

This is NOT authoritative exchange-calendar verification or session acceptance.
"""
import datetime as dt
from zoneinfo import ZoneInfo
from deploy.phase0_lineage_negative_gate import assess_lineage_evidence

IST = ZoneInfo("Asia/Kolkata")


def assess_scheduled_close(record):
    result = assess_lineage_evidence(record)
    if result != "ELIGIBLE_FOR_EXTERNAL_CORROBORATION":
        return result
    start = record["worker_started_at"].astimezone(IST)
    end = record["worker_ended_at"].astimezone(IST)
    terminal = record["terminal_events"][0]["timestamp"].astimezone(IST)
    if start.weekday() >= 5:
        return "BLOCKED_WEEKEND"
    # A scheduled close cannot precede the documented 15:30 IST boundary.
    boundary = dt.datetime.combine(start.date(), dt.time(15, 30), IST)
    if terminal < boundary or end < boundary:
        return "BLOCKED_PREMATURE_SCHEDULED_CLOSE"
    # Never promote a clock check to verified calendar/coverage authority.
    return "ELIGIBLE_FOR_EXTERNAL_CALENDAR_AND_PROVENANCE_REVIEW"
