"""Phase 0: GET-only Firestore latest/history/nightly internal reconciliation.

No financial values, document IDs or credentials are logged. MATCH is only
consistency between Firestore read models, never journal/broker reconciliation.
"""
from __future__ import annotations

import math
import os
import sys

from deploy.phase0_firestore_journal_reconcile import as_number


def comparable(x, y):
    if x is None or y is None:
        return x is None and y is None
    if isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(y, (int, float)) and not isinstance(y, bool):
        return math.isclose(float(x), float(y), rel_tol=0, abs_tol=0.011)
    return x == y


def validate_day(row):
    """Conservative consistency check; no unknown count is coerced to zero."""
    if row.get("data_type") != "PAPER_SIMULATION":
        return "UNVERIFIED_DATA_TYPE"
    closed = row.get("closed_trades")
    covered = row.get("pnl_coverage")
    if any(not isinstance(x, int) or isinstance(x, bool) for x in (closed, covered)):
        return "MISSING_COVERAGE_COUNTER"
    if covered < 0 or closed < 0 or covered > closed:
        return "INVALID_COVERAGE"
    net = as_number(row.get("net_pnl"))
    if covered and net is None:
        return "MISSING_NET_PNL"
    if not covered and net is not None:
        return "UNEXPECTED_NET_PNL"
    if covered < closed:
        return "PARTIAL_FINANCIAL_COVERAGE"
    stats = row.get("strategy_stats")
    if closed == 0:
        return "MATCH" if not stats else "UNEXPECTED_STRATEGY_TRADES"
    if not isinstance(stats, dict) or not stats:
        return "MISSING_STRATEGY_STATS"
    total_count = 0
    total_verified = 0
    total_net = 0.0
    for obj in stats.values():
        if not isinstance(obj, dict):
            return "INVALID_STRATEGY_STATS"
        count = obj.get("closed_trades")
        coverage = obj.get("verified_trades")
        if any(not isinstance(x, int) or isinstance(x, bool) for x in (count, coverage)):
            return "MISSING_STRATEGY_COUNTERS"
        if count < 0 or coverage < 0 or coverage > count:
            return "INVALID_STRATEGY_COVERAGE"
        pnl = as_number(obj.get("net_pnl"))
        if coverage and pnl is None:
            return "MISSING_STRATEGY_PNL"
        total_count += count
        total_verified += coverage
        total_net += pnl or 0.0
    if total_count != closed or total_verified != covered:
        return "STRATEGY_COUNT_MISMATCH"
    if net is None or not comparable(round(total_net, 2), round(net, 2)):
        return "STRATEGY_PNL_MISMATCH"
    return "MATCH"


def compare_latest(latest, historical):
    for key in ("date_ist", "market", "run_id", "closed_trades",
                "pnl_coverage", "signals_count", "entry_event_count",
                "net_pnl", "gross_pnl", "fees_total", "strategy_stats"):
        if not comparable(latest.get(key), historical.get(key)):
            return "LATEST_HISTORY_FIELD_MISMATCH_" + key.upper()
    return "MATCH"


def compare_evaluation(report, days):
    if not days:
        return "NO_HISTORY_FOR_DATE"
    for row in days:
        if any(not isinstance(row.get(key), int) or isinstance(row.get(key), bool)
               or row[key] < 0 for key in ("closed_trades", "pnl_coverage")):
            return "EVALUATION_INVALID_HISTORY_COUNTERS"
        if row["pnl_coverage"] > row["closed_trades"]:
            return "EVALUATION_INVALID_HISTORY_COVERAGE"
    closed = sum(x["closed_trades"] for x in days)
    coverage = sum(x["pnl_coverage"] for x in days)
    if not comparable(report.get("closed_trades"), closed) or not comparable(report.get("verified_pnl_trades"), coverage):
        return "EVALUATION_COUNTER_MISMATCH"
    if coverage < closed:
        return "EVALUATION_PARTIAL_FINANCIAL_COVERAGE"
    if coverage:
        if any(as_number(x.get("net_pnl")) is None
               for x in days if isinstance(x.get("pnl_coverage"), int)
               and x["pnl_coverage"] > 0):
            return "EVALUATION_INCOMPLETE_COVERAGE"
        total = sum(as_number(x.get("net_pnl")) or 0.0 for x in days)
        if not comparable(report.get("net_pnl"), round(total, 2)):
            return "EVALUATION_NET_MISMATCH"
    elif report.get("net_pnl") is not None:
        return "EVALUATION_UNEXPECTED_NET"
    return "MATCH"


def firestore_get_collections():
    import json
    import google.oauth2.service_account
    from google.auth.transport.requests import AuthorizedSession
    from deploy.nightly_strategy_evaluation import unpack
    raw = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET"])
    credentials = google.oauth2.service_account.Credentials.from_service_account_info(
        raw, scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    base = ("https://firestore.googleapis.com/v1/projects/" +
            os.environ["FIREBASE_PROJECT_ID"] + "/databases/(default)/documents/")
    result = {}
    for name in ("paper_dashboard", "paper_history", "paper_evaluations"):
        rows = []
        token = None
        for index in range(3):
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            response = session.get(base + name, params=params, timeout=25)
            response.raise_for_status()
            data = response.json()
            rows.extend((entry.get("name", "").rsplit("/", 1)[-1],
                         {k: unpack(v) for k, v in entry.get("fields", {}).items()})
                        for entry in data.get("documents", []))
            token = data.get("nextPageToken")
            if not token:
                break
        if token:
            raise RuntimeError("Firestore pagination sample limit reached")
        result[name] = rows
    return result


def main():
    if not os.getenv("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET") or not os.getenv("FIREBASE_PROJECT_ID"):
        print("PHASE0_INTERNAL_RECONCILE=UNAVAILABLE reason=MISSING_CONFIG")
        return 2
    try:
        docs = firestore_get_collections()
        history = [r for _, r in docs["paper_history"] if r.get("data_type") == "PAPER_SIMULATION"]
        from deploy.phase0_duplicate_provenance import classify_history_groups
        duplicate_audit = classify_history_groups(history)
        if duplicate_audit["duplicate_groups"]:
            print("PHASE0_INTERNAL_RECONCILE=BLOCKED reason=DUPLICATE_HISTORY_KEYS"
                  " duplicate_groups=" + str(duplicate_audit["duplicate_groups"])
                  + " (session identity/termination unverified)", flush=True)
            return 4
        by_key = {}
        for row in history:
            k = (row.get("date_ist"), row.get("market"))
            current = by_key.get(k)
            if current is None or str(row.get("updated_at") or "") > str(current.get("updated_at") or ""):
                by_key[k] = row
        outcomes = []
        for (day, market), row in sorted(by_key.items()):
            reason = validate_day(row)
            outcomes.append(reason)
            print("INTERNAL_HISTORY date=" + str(day) + " market=" + str(market) +
                  " outcome=" + reason, flush=True)
        for doc_id, row in docs["paper_dashboard"]:
            if not doc_id.startswith("latest_"):
                continue
            key = (row.get("date_ist"), row.get("market"))
            source = by_key.get(key)
            reason = compare_latest(row, source) if source else "MISSING_MATCHING_HISTORY"
            outcomes.append(reason)
            print("INTERNAL_LATEST market=" + str(row.get("market", "UNKNOWN")) +
                  " outcome=" + reason, flush=True)
        for doc_id, report in docs["paper_evaluations"]:
            if doc_id == "latest":
                continue
            date = report.get("report_date")
            same_date = [row for (d, _), row in by_key.items() if d == date]
            reason = compare_evaluation(report, same_date)
            outcomes.append(reason)
            print("INTERNAL_EVALUATION date=" + str(date) + " outcome=" + reason, flush=True)
        if not outcomes:
            print("PHASE0_INTERNAL_RECONCILE=BLOCKED reason=EMPTY_COLLECTIONS", flush=True)
            return 4
        errors = [reason for reason in outcomes if reason != "MATCH"]
        print("PHASE0_INTERNAL_RECONCILE=" +
              ("INCONSISTENT" if errors else "FIRESTORE_READ_MODELS_MATCH") +
              " checked=" + str(len(outcomes)) + " issues=" + str(len(errors)) +
              " (not private-archive/broker reconciled)", flush=True)
        return 4 if errors else 0
    except Exception as exc:
        print("PHASE0_INTERNAL_RECONCILE=FAILED exception_type=" +
              type(exc).__name__, flush=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
