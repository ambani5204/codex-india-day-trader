"""Phase 0: bounded read-only Firestore schema evidence. Never prints values/IDs.

This diagnostics module only permits GET. No Firestore write paths or broker calls.
A SUCCESS here proves sampled schema access, not a full ledger reconciliation.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys

COLLECTIONS = (
    "paper_dashboard",
    "paper_history",
    "paper_evaluations",
    "three_candle_paper",
    "ema9_ema15_paper",
    "three_candle_nightly",
)
ALLOWED_FIELD_TYPES = frozenset({
    "nullValue", "booleanValue", "integerValue", "doubleValue", "stringValue",
    "arrayValue", "mapValue", "timestampValue", "referenceValue",
    "geoPointValue", "bytesValue",
})
MAX_PAGES = 3
PAGE_SIZE = 100


def type_summary(fields):
    """Return key→sorted type-set without reading, storing or printing values."""
    summary = {}
    for key, typed in fields.items():
        types = sorted(set(typed).intersection(ALLOWED_FIELD_TYPES)) if isinstance(typed, dict) else []
        summary[str(key)] = types or ["UNRECOGNIZED"]
    return summary


def merge_types(target, fields):
    for name, variants in type_summary(fields).items():
        target.setdefault(name, set()).update(variants)


def scan_collection(session, base, name):
    types = {}
    count = 0
    token = None
    pages = 0
    while pages < MAX_PAGES:
        params = {"pageSize": PAGE_SIZE}
        if token:
            params["pageToken"] = token
        response = session.get(base + name, params=params, timeout=25)
        if response.status_code == 404:
            return {"collection": name, "state": "MISSING", "sampled": 0,
                    "page_cap_reached": False, "field_types": {}}
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("documents", []):
            count += 1
            merge_types(types, row.get("fields", {}))
        token = payload.get("nextPageToken")
        pages += 1
        if not token:
            break
    return {"collection": name, "state": "SAMPLED" if count else "EMPTY",
            "sampled": count, "page_cap_reached": bool(token),
            "field_types": {key: sorted(values) for key, values in sorted(types.items())}}


def main():
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", "")
    project = os.getenv("FIREBASE_PROJECT_ID", "")
    if not raw or not project:
        print("PHASE0_FIRESTORE_PROBE=UNAVAILABLE reason=MISSING_CONFIGURATION", flush=True)
        return 2
    try:
        import google.oauth2.service_account
        from google.auth.transport.requests import AuthorizedSession
        credentials = google.oauth2.service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=["https://www.googleapis.com/auth/datastore"])
        session = AuthorizedSession(credentials)
        base = ("https://firestore.googleapis.com/v1/projects/" +
                project + "/databases/(default)/documents/")
        results = [scan_collection(session, base, name) for name in COLLECTIONS]
    except Exception as exc:
        # Do NOT log server response bodies, credentials or URLs.
        print("PHASE0_FIRESTORE_PROBE=FAILED exception_type=" +
              type(exc).__name__, flush=True)
        return 3
    for row in results:
        # The schema includes *types only*, not Firestore values or document names.
        canonical = json.dumps(row["field_types"], sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        print("SCHEMA_COLLECTION=" + row["collection"] +
              " state=" + row["state"] +
              " sampled=" + str(row["sampled"]) +
              " capped=" + str(row["page_cap_reached"]).lower() +
              " fields=" + str(len(row["field_types"])) +
              " field_type_sha256=" + fingerprint, flush=True)
        print("SCHEMA_FIELD_TYPES=" + row["collection"] + " " +
              canonical, flush=True)
    print("PHASE0_FIRESTORE_PROBE=READ_ONLY_SAMPLE_COMPLETE; NOT_LEDGER_RECONCILIATION",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
