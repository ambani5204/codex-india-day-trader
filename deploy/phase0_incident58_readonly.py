"""Incident #58: bounded, credentialed Firestore GET-only metadata audit.

Never print document bodies, financial values, private identifiers or secrets.
An update timestamp cannot independently establish source/journal equality.
"""
from __future__ import annotations

import datetime as dt
import json
import os

EXPECTED_PROJECT = "stock-market-c5016"
INCIDENT_STARTED_UTC = dt.datetime(2026, 11, 23, 17, 18, 14, tzinfo=dt.timezone.utc)
AFFECTED = (
    ("2026-11-13", "NIFTY"),
    ("2026-11-16", "NIFTY"),
    ("2026-11-19", "NIFTY"),
    ("2026-11-20", "SENSEX"),
)


def inspect_get_only(session, project: str = EXPECTED_PROJECT) -> list[dict]:
    """Read precisely four immutable document paths. Never return content."""
    if project != EXPECTED_PROJECT:
        raise ValueError("Unexpected Firebase project")
    base = ("https://firestore.googleapis.com/v1/projects/"
            + project + "/databases/(default)/documents/paper_history/")
    outcomes = []
    for day, market in AFFECTED:
        name = base.split("https://firestore.googleapis.com/v1/", 1)[1] + day + "_" + market
        response = session.get(base + day + "_" + market, timeout=25)
        if response.status_code == 404:
            code = "MISSING_DOCUMENT"
        else:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("name") != name:
                code = "INVALID_DOCUMENT_METADATA"
            elif not isinstance(payload.get("fields"), dict):
                code = "INVALID_FIELD_MAP"
            elif (payload["fields"].get("data_type") or {}).get("stringValue") != "PAPER_SIMULATION":
                code = "UNVERIFIED_DATA_TYPE"
            else:
                updated = payload.get("updateTime")
                try:
                    if not isinstance(updated, str):
                        raise ValueError("Absent update timestamp")
                    timestamp = dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if timestamp.tzinfo is None:
                        raise ValueError("Timezone missing")
                    code = ("PRESENT_MODIFIED_SINCE_INCIDENT"
                            if timestamp.astimezone(dt.timezone.utc) >= INCIDENT_STARTED_UTC
                            else "PRESENT_OLDER_MODIFICATION")
                except (TypeError, ValueError, OverflowError):
                    code = "INVALID_UPDATE_TIMESTAMP"
        outcomes.append({"date": day, "market": market, "status": code})
    return outcomes


def main() -> int:
    if os.environ.get("FIREBASE_PROJECT_ID") != EXPECTED_PROJECT:
        print("INCIDENT58_METADATA=UNAVAILABLE reason=PROJECT_NOT_VERIFIED", flush=True)
        return 2
    secret = os.environ.get("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", "")
    if not secret:
        print("INCIDENT58_METADATA=UNAVAILABLE reason=CREDENTIALS_NOT_PRESENT", flush=True)
        return 2
    try:
        import google.oauth2.service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(secret)
        if info.get("project_id") != EXPECTED_PROJECT:
            raise ValueError("Service account project mismatch")
        credentials = google.oauth2.service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/datastore"])
        results = inspect_get_only(AuthorizedSession(credentials))
    except Exception as exc:
        # No raw exception: HTTP errors or credential libraries may contain private URLs.
        print("INCIDENT58_METADATA=BLOCKED reason=" + type(exc).__name__, flush=True)
        return 4
    for item in results:
        print("INCIDENT58_GET date=" + item["date"] + " market=" + item["market"]
              + " status=" + item["status"], flush=True)
    valid = sum(r["status"] == "PRESENT_MODIFIED_SINCE_INCIDENT" for r in results)
    print("INCIDENT58_METADATA=" + ("PRESENT_TIMESTAMP_ONLY" if valid == len(AFFECTED)
                                     else "INCOMPLETE")
          + " checked=" + str(len(results)) + " post_run_timestamp=" + str(valid)
          + " lineage_and_values=UNVERIFIED", flush=True)
    return 0 if valid == len(AFFECTED) else 4


if __name__ == "__main__":
    raise SystemExit(main())
