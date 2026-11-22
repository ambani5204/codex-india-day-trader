"""Fail-closed, synthetic-safe identity diagnostics for private Phase 0 audits.

This helper performs no I/O. Callers must not log events, identifiers or P&L.
It does not assert Firestore parity or infer immutable restart lineage.
"""
from collections import Counter

EVENT_KEYS = {
    "INDEX_SIGNAL": "signal_id",
    "PAPER_TRADE_CLOSED": "trade_id",
    "SESSION_SUMMARY": "session_id",
}


def identity_diagnostics(events, expected=None):
    """Return aggregate-only reason codes; never return identifiers or values.

    expected, when provided, is a separate source's event list. No identity
    comparison is certified if provenance or required IDs are unavailable.
    """
    def scan(items):
        seen = {}
        missing = Counter()
        duplicate = Counter()
        invalid = 0
        for item in items:
            if not isinstance(item, dict):
                invalid += 1
                continue
            kind = item.get("event")
            if kind not in EVENT_KEYS:
                continue
            field = EVENT_KEYS[kind]
            identifier = item.get(field)
            if not isinstance(identifier, str) or not identifier.strip():
                missing[kind] += 1
                continue
            # A key is unique within a known event kind; do not deduplicate
            # legitimate distinct kinds that happen to share a string ID.
            key = (kind, identifier.strip())
            if key in seen:
                duplicate[kind] += 1
            seen[key] = True
        return set(seen), missing, duplicate, invalid

    left, missing, duplicate, invalid = scan(events)
    reasons = set()
    if invalid:
        reasons.add("INVALID_EVENT_SHAPE")
    if missing:
        reasons.add("MISSING_EVENT_ID")
    if duplicate:
        reasons.add("DUPLICATE_EVENT_ID")
    if expected is not None:
        right, other_missing, other_duplicate, other_invalid = scan(expected)
        if other_invalid:
            reasons.add("INVALID_COUNTERPART_EVENT_SHAPE")
        if other_missing:
            reasons.add("MISSING_COUNTERPART_EVENT_ID")
        if other_duplicate:
            reasons.add("DUPLICATE_COUNTERPART_EVENT_ID")
        if left != right:
            reasons.add("EVENT_IDENTITY_MISMATCH")
    # Even exact event-ID equality does not prove immutable session provenance.
    reasons.add("SESSION_LINEAGE_UNVERIFIED")
    return {"status": "BLOCKED", "reasons": sorted(reasons),
            "missing_count": sum(missing.values()),
            "duplicate_count": sum(duplicate.values()),
            "invalid_count": invalid}
