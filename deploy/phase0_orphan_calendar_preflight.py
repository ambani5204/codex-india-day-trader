"""Pure, read-only orphan/calendar preflight; never mutates Firestore.

This is an investigation aid, NOT proof of provenance. A Saturday evaluation
must be preserved and investigated, not automatically labeled legacy.
"""
import datetime as dt


def assess_evaluation_lineage(report_date, evaluation, history_rows, *, holidays=()):
    """Return privacy-safe anomaly codes, not identifiers or financial values."""
    try:
        date = dt.date.fromisoformat(report_date)
    except (TypeError, ValueError):
        return {"status": "BLOCKED_INVALID_DATE", "matched_sessions": 0}
    if not isinstance(evaluation, dict):
        return {"status": "BLOCKED_MISSING_EVALUATION", "matched_sessions": 0}
    if date.weekday() >= 5:
        calendar_status = "WEEKEND"
    elif report_date in holidays:
        calendar_status = "HOLIDAY"
    else:
        calendar_status = "CALENDAR_NOT_VERIFIED"
    eligible = [r for r in history_rows if isinstance(r, dict)
                and r.get("data_type") == "PAPER_SIMULATION"
                and r.get("date_ist") == report_date
                and r.get("market") in ("NIFTY", "SENSEX")]
    if not eligible:
        return {"status": "BLOCKED_NO_ELIGIBLE_HISTORY",
                "calendar_status": calendar_status, "matched_sessions": 0,
                "provenance": "UNDETERMINED"}
    missing_session_identity = any(not r.get("session_id") for r in eligible)
    return {"status": "BLOCKED_SESSION_IDENTITY" if missing_session_identity
            else "REQUIRES_EVENT_RECONCILIATION",
            "calendar_status": calendar_status, "matched_sessions": len(eligible),
            "provenance": "UNDETERMINED"}
