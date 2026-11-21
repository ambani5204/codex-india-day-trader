"""Credentialed GET-only aggregate diagnostic. Never prints Firestore document IDs.

Requires the same read-only Firestore environment as the existing Phase 0
internal reconciliation. Does not write, delete or repair any documents.
"""
import os
import sys

from deploy.phase0_firestore_internal_reconcile import (
    firestore_get_collections, select_paper_history,
)
from deploy.phase0_session_lineage_diagnostics import (
    classify_market_date_lineage, safe_summary,
)


def main():
    if not os.getenv("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET") or not os.getenv("FIREBASE_PROJECT_ID"):
        print("PHASE0_LINEAGE=UNAVAILABLE reason=MISSING_CONFIG")
        return 2
    try:
        docs = firestore_get_collections()
        status, rows = select_paper_history([row for _, row in docs["paper_history"]])
        if status != "MATCH":
            print("PHASE0_LINEAGE=BLOCKED reason=" + status)
            return 4
        result = classify_market_date_lineage(rows)
        print(safe_summary(result))
        # Zero ambiguous market/date groups is not proof of journal reconciliation.
        return 4 if result["status"] != "NO_MULTIROW_GROUPS" else 0
    except Exception as exc:
        print("PHASE0_LINEAGE=FAILED exception_type=" + type(exc).__name__)
        return 3


if __name__ == "__main__":
    sys.exit(main())
