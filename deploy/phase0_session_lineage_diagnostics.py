"""Privacy-safe, offline session-lineage diagnostics for duplicate market/date history.

No network calls, mutations, raw IDs, financial values or event payloads in output.
A unique run_id is evidence of *different claimed runs*, not proof of a
legitimate restart or disjoint trade events. Always fail closed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as calendar_date


def _usable(value):
    return isinstance(value, str) and bool(value.strip())


def classify_market_date_lineage(rows):
    """Return aggregate-only evidence and a fail-closed classification.

    A verified daily P&L requires journal-backed session lifecycle and unique
    trade-event reconciliation; this function never certifies that condition.
    """
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        return {"status": "INVALID_ROWS", "groups": 0, "ambiguous_groups": 0,
                "different_run_groups": 0, "same_run_groups": 0,
                "missing_run_groups": 0}
    groups = defaultdict(list)
    missing_identity_rows = 0
    for row in rows:
        if row.get("data_type") != "PAPER_SIMULATION":
            continue
        date, market = row.get("date_ist"), row.get("market")
        try:
            parsed_date = calendar_date.fromisoformat(date) if isinstance(date, str) else None
        except ValueError:
            parsed_date = None
        if parsed_date is None or parsed_date.isoformat() != date or market not in {"NIFTY", "SENSEX"}:
            return {"status": "INVALID_HISTORY_KEY", "groups": 0,
                    "ambiguous_groups": 0, "different_run_groups": 0,
                    "same_run_groups": 0, "missing_run_groups": 0}
        if not _usable(row.get("run_id")):
            missing_identity_rows += 1
        groups[(date, market)].append(row)
    counters = {"groups": len(groups), "ambiguous_groups": 0,
                "different_run_groups": 0, "same_run_groups": 0,
                "missing_run_groups": 0}
    for group in groups.values():
        if len(group) < 2:
            continue
        counters["ambiguous_groups"] += 1
        ids = [r.get("run_id") for r in group]
        if any(not _usable(v) for v in ids):
            counters["missing_run_groups"] += 1
        elif len(set(ids)) == len(ids):
            counters["different_run_groups"] += 1
        else:
            counters["same_run_groups"] += 1
    return {"status": "BLOCKED_LINEAGE_UNVERIFIED" if counters["ambiguous_groups"]
            else "BLOCKED_MISSING_RUN_ID" if missing_identity_rows
            else "NO_MULTIROW_GROUPS", **counters}


def safe_summary(result):
    """Print only allowlisted aggregate categories and counts, never identifiers."""
    allowed = ("groups", "ambiguous_groups", "different_run_groups",
               "same_run_groups", "missing_run_groups")
    statuses = {"INVALID_ROWS", "INVALID_HISTORY_KEY",
                "BLOCKED_LINEAGE_UNVERIFIED", "BLOCKED_MISSING_RUN_ID",
                "NO_MULTIROW_GROUPS"}
    status = result.get("status")
    if status not in statuses or any(type(result.get(k)) is not int or result[k] < 0
                                     for k in allowed):
        return "PHASE0_LINEAGE=INVALID_SUMMARY"
    return "PHASE0_LINEAGE=" + status + " " + " ".join(
        k + "=" + str(result[k]) for k in allowed)
