"""Offline, read-only Phase 0 evaluation linkage classification.

This module does not access or mutate Firestore. Classification is not an
authorization to archive, delete or manufacture missing paper sessions.
"""
from datetime import date


def classify_evaluation(evaluation, history, expected_date):
    """Return only status and issue codes; do not expose private ledger values."""
    issues = set()
    try:
        day = date.fromisoformat(expected_date)
    except (ValueError, TypeError):
        return {"status": "UNKNOWN", "issues": ["INVALID_DATE"]}
    if not isinstance(evaluation, dict):
        return {"status": "UNKNOWN", "issues": ["EVALUATION_MISSING"]}
    if not isinstance(history, list):
        return {"status": "UNKNOWN", "issues": ["HISTORY_UNAVAILABLE"]}
    if evaluation.get("report_date", expected_date) != expected_date:
        issues.add("REPORT_DATE_MISMATCH")
    eligible = [r for r in history if isinstance(r, dict)
                and r.get("date_ist") == expected_date
                and r.get("data_type") == "PAPER_SIMULATION"]
    if not eligible:
        issues.add("NO_ELIGIBLE_HISTORY")
        if day.weekday() >= 5:
            issues.add("WEEKEND_EVALUATION_REQUIRES_PROVENANCE")
    else:
        runs = {r.get("run_id") for r in eligible}
        if None in runs or "" in runs:
            issues.add("HISTORY_RUN_ID_MISSING")
        if len(runs) > 1:
            issues.add("MULTIPLE_HISTORY_RUNS")
        source_run = evaluation.get("run_id")
        if not source_run:
            issues.add("EVALUATION_RUN_ID_MISSING")
        elif source_run not in runs:
            issues.add("EVALUATION_RUN_NOT_IN_HISTORY")
    return {"status": "RECONCILIATION_PENDING" if issues else "LINKED_BY_RUN_ID",
            "issues": sorted(issues)}
