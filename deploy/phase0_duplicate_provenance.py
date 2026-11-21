"""Phase 0 privacy-safe duplicate history provenance classifier.

Pure offline/read-only diagnostic. Never returns identifiers, P&L or trade details.
No classification grants reconciliation or release qualification.
"""
from collections import defaultdict


def classify_history_groups(rows):
    groups = defaultdict(list)
    for row in rows:
        market, day = row.get("market"), row.get("date_ist")
        if market not in {"NIFTY", "SENSEX"} or not isinstance(day, str) or not day:
            continue
        groups[(day, market)].append(row)

    result = {
        "duplicate_groups": 0,
        "duplicate_rows": 0,
        "missing_session_identity": 0,
        "repeated_session_identity": 0,
        "distinct_session_groups": 0,
        "unverified_groups": 0,
    }
    for entries in groups.values():
        if len(entries) < 2:
            continue
        result["duplicate_groups"] += 1
        result["duplicate_rows"] += len(entries)
        ids = [r.get("session_id") for r in entries]
        valid = [s for s in ids if isinstance(s, str) and s.strip()]
        result["missing_session_identity"] += len(ids) - len(valid)
        result["repeated_session_identity"] += len(valid) - len(set(valid))
        if len(valid) == len(ids) and len(set(valid)) == len(valid):
            result["distinct_session_groups"] += 1
        # Even distinct IDs cannot prove completed sessions, ledger lineage or
        # that duplicate documents represent legitimate restart attempts.
        result["unverified_groups"] += 1
    return result


def classify_orphan_evaluation(report_date, histories, evaluation):
    """Fail closed: a Saturday evaluation is not automatically stale/legacy."""
    import datetime as dt
    try:
        day = dt.date.fromisoformat(report_date)
    except (TypeError, ValueError):
        return "INVALID_REPORT_DATE"
    if not isinstance(evaluation, dict):
        return "EVALUATION_UNAVAILABLE"
    eligible = [r for r in histories
                if r.get("date_ist") == report_date
                and r.get("data_type") == "PAPER_SIMULATION"]
    if not eligible:
        return "NO_ELIGIBLE_HISTORY_WEEKEND" if day.weekday() >= 5 else "NO_ELIGIBLE_HISTORY"
    if len(eligible) != 1:
        return "AMBIGUOUS_HISTORY"
    report_id = evaluation.get("run_id")
    history_id = eligible[0].get("run_id")
    if not isinstance(report_id, str) or not report_id.strip() or not isinstance(history_id, str) or not history_id.strip():
        return "MISSING_RUN_PROVENANCE"
    if report_id != history_id:
        return "RUN_PROVENANCE_MISMATCH"
    return "IDENTITY_MATCH_TERMINATION_UNVERIFIED"
