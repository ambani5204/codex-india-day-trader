"""Fail-closed, offline-only evidence preflight for paper session termination.

Not a workflow change or a claim of real market acceptance.
"""
import datetime as dt
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def assess_termination(record):
    """Return code only. Never infer worker completion from CI job success."""
    if not isinstance(record, dict) or not record.get("session_id") or not record.get("attempt_id"):
        return "BLOCKED_MISSING_SESSION_IDENTITY"
    if record.get("data_type") != "PAPER_SIMULATION":
        return "BLOCKED_UNVERIFIED_DATA_TYPE"
    if record.get("workflow_conclusion") == "success" and not record.get("worker_exit_reason"):
        return "BLOCKED_CI_SUCCESS_NOT_TERMINATION"
    started, ended = record.get("worker_started_at"), record.get("worker_ended_at")
    if not isinstance(started, dt.datetime) or not isinstance(ended, dt.datetime):
        return "BLOCKED_MISSING_WORKER_TIMESTAMPS"
    if started.tzinfo is None or ended.tzinfo is None or ended <= started:
        return "BLOCKED_INVALID_WORKER_TIMESTAMPS"
    local_start, local_end = started.astimezone(IST), ended.astimezone(IST)
    if local_start.date() != local_end.date():
        return "BLOCKED_CROSS_DATE_REQUIRES_REVIEW"
    if local_end.time() < dt.time(15, 30):
        # Early failure/restart may be legitimate but is not a completed full session.
        return "BLOCKED_EARLY_EXIT_REQUIRES_LINEAGE"
    if record.get("worker_exit_reason") != "SCHEDULED_MARKET_CLOSE":
        return "BLOCKED_EXIT_REASON_REQUIRES_REVIEW"
    if record.get("journal_reconciled") is not True:
        return "BLOCKED_JOURNAL_RECONCILIATION"
    if record.get("calendar_verified") is not True:
        return "BLOCKED_CALENDAR_UNVERIFIED"
    return "ELIGIBLE_FOR_INDEPENDENT_ACCEPTANCE"
