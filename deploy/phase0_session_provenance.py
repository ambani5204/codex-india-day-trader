"""Offline, fail-closed comparison of independently sourced session provenance.

No network, private identifiers in output, or production mutations.
Inputs must be separately extracted from journal and Firestore; this function
cannot authenticate the origin of caller-supplied manifests.
"""
from collections import Counter

REQUIRED = ("session_id", "run_id", "market_date", "market", "started_at")

def audit_session_provenance(journal, firestore):
    """Return aggregate-only reason codes; never return private keys or values."""
    if journal is None or firestore is None:
        return {"ok": False, "reason": "MISSING_INDEPENDENT_MANIFEST"}
    def inspect(rows):
        if not isinstance(rows, (list, tuple)) or not rows:
            return None, "EMPTY_OR_INVALID_MANIFEST"
        keys = []
        sessions = {}
        for row in rows:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in REQUIRED):
                return None, "MISSING_PROVENANCE_FIELD"
            key = tuple(row[k] for k in REQUIRED)
            keys.append(key)
            session = row["session_id"]
            lineage = (row["run_id"], row["market_date"], row["market"], row["started_at"])
            if session in sessions and sessions[session] != lineage:
                return None, "AMBIGUOUS_SESSION_RESTART"
            sessions[session] = lineage
        if len(keys) != len(set(keys)):
            return None, "DUPLICATE_PROVENANCE_RECORD"
        return Counter(keys), None
    left, error = inspect(journal)
    if error:
        return {"ok": False, "reason": "JOURNAL_" + error}
    right, error = inspect(firestore)
    if error:
        return {"ok": False, "reason": "FIRESTORE_" + error}
    if left != right:
        return {"ok": False, "reason": "SESSION_PROVENANCE_MISMATCH"}
    return {"ok": True, "reason": "MANIFEST_FIELDS_MATCH_ONLY"}
