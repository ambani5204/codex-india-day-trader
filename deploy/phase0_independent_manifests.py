"""Offline independent manifest gate. No private IDs or records in results."""
from collections import Counter
from deploy.phase0_event_accounting import audit_event_accounting

FIELDS = ("session_id", "run_id", "started_at", "market_date", "strategy")

def audit_independent_manifests(journal_sessions, firestore_sessions, journal_events, firestore_events):
    """Compare independently extracted provenance before event/accounting equality.

    This cannot authenticate extraction origin or prove collection completeness.
    """
    def normalize(rows, source):
        if not isinstance(rows, (list, tuple)) or not rows:
            return None, source + "_MISSING_MANIFEST"
        identities = []
        for row in rows:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in FIELDS):
                return None, source + "_INVALID_PROVENANCE"
            identities.append(tuple(row[k] for k in FIELDS))
        if len(identities) != len(set(identities)):
            return None, source + "_DUPLICATE_PROVENANCE"
        keys = [(v[0], v[1]) for v in identities]
        if len(keys) != len(set(keys)):
            return None, source + "_AMBIGUOUS_SESSION"
        run_ids = [v[1] for v in identities]
        if len(run_ids) != len(set(run_ids)):
            return None, source + "_REUSED_RUN_ID"
        return Counter(identities), None

    left, error = normalize(journal_sessions, "JOURNAL")
    if error:
        return {"ok": False, "reason": error}
    right, error = normalize(firestore_sessions, "FIRESTORE")
    if error:
        return {"ok": False, "reason": error}
    if left != right:
        return {"ok": False, "reason": "INDEPENDENT_SESSION_PROVENANCE_MISMATCH"}
    result = audit_event_accounting(journal_sessions, journal_events, firestore_events)
    if not result["ok"]:
        return result
    return {"ok": True, "reason": "SUPPLIED_MANIFESTS_AND_EVENTS_MATCH_ONLY"}
