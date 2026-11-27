"""Phase-0 offline event identity gate. No network, credentials, writes or raw IDs in output.

This gate does not infer Firestore event identity from aggregate counters. The caller
must provide an independently sourced identity manifest; absent provenance blocks.
"""
from collections import Counter

KINDS = {"INDEX_SIGNAL": "signal_id", "PAPER_TRADE_CLOSED": "trade_id",
         "SESSION_SUMMARY": "session_id"}
def _ids(events):
    result = []
    for event in events:
        if not isinstance(event, dict):
            return None, "MALFORMED_EVENT"
        kind = event.get("event")
        if kind not in KINDS:
            continue
        identifier = event.get(KINDS[kind])
        if not isinstance(identifier, str) or not identifier or identifier != identifier.strip():
            return None, "MISSING_OR_INVALID_ID"
        result.append((kind, identifier))
    if len(result) != len(set(result)):
        return None, "REPEATED_EVENT_ID"
    return Counter(result), None

def compare_event_identity(archive_events, firestore_manifest=None, provenance_verified=False):
    """Return reason code only. Never serialize event identifiers into logs.

    firestore_manifest is an independently acquired collection of event records
    with the same identity fields; paper_history counters are NOT such a manifest.
    provenance_verified must only be true after independent session/run lineage
    evidence is checked, not inferred from different run IDs.
    """
    archive, error = _ids(archive_events)
    if error:
        return error
    if firestore_manifest is None:
        return "FIRESTORE_EVENT_MANIFEST_MISSING"
    remote, error = _ids(firestore_manifest)
    if error:
        return "FIRESTORE_" + error
    if archive != remote:
        return "EVENT_IDENTITY_MISMATCH"
    if not provenance_verified:
        return "RESTART_PROVENANCE_UNVERIFIED"
    return "EVENT_IDENTITIES_MATCH_PROVENANCE_ATTESTED"
