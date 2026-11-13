"""Safe Firebase smoke test: disposable write/read/delete plus dashboard presence check."""
import json
import os
import sys
import uuid
import datetime as dt

PROJECT = "stock-market-c5016"
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"

def check(response, label):
    if not response.ok:
        hint = {400:"invalid request or database", 401:"invalid token", 403:"service account lacks Firestore permissions or API disabled", 404:"document/database missing", 429:"quota exceeded"}.get(response.status_code, "server/network error")
        raise RuntimeError(f"{label}: Firestore HTTP {response.status_code} ({hint})")
    return response

def main():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", "")
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET secret missing")
    info = json.loads(raw)
    if info.get("type") != "service_account" or info.get("project_id") != PROJECT:
        raise RuntimeError("Invalid service account type or Firebase project")
    if not info.get("client_email", "").startswith("paper-trading-publisher@"):
        raise RuntimeError("Unexpected service account identity")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    print("CREDENTIAL FORMAT OK: project and publisher identity match", flush=True)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    try:
        credentials.refresh(__import__("google.auth.transport.requests", fromlist=["Request"]).Request())
    except Exception as exc:
        raise RuntimeError("GOOGLE AUTH FAILED: check private key, service account enabled status, and token permissions (" + type(exc).__name__ + ")") from exc
    print("GOOGLE AUTH OK", flush=True)
    url = BASE + "/_connection_tests/smoke_" + uuid.uuid4().hex
    created = False
    try:
        response = check(session.patch(url, json={"fields": {"status": {"stringValue": "ok"}}}, timeout=25), "WRITE")
        created = True
        print("WRITE OK", flush=True)
        response = check(session.get(url, timeout=25), "READ")
        if response.json().get("fields", {}).get("status", {}).get("stringValue") != "ok":
            raise RuntimeError("READ returned unexpected data")
        print("READ OK", flush=True)
    finally:
        if created:
            check(session.delete(url, timeout=25), "CLEANUP")
            print("CLEANUP OK", flush=True)

    dashboard_present = False
    dashboard = session.get(BASE + "/paper_dashboard/latest", timeout=25)
    if dashboard.status_code == 404:
        print("DASHBOARD MISSING: trading publisher has not created paper_dashboard/latest", flush=True)
    else:
        check(dashboard, "DASHBOARD READ")
        dashboard_present = True
        fields = dashboard.json().get("fields", {})
        print("DASHBOARD FOUND: status=" + str(fields.get("session_status", {}).get("stringValue", "unknown")) +
              " updated_at=" + str(fields.get("updated_at", {}).get("stringValue", "unknown")), flush=True)
    history = session.get(BASE + "/paper_history?pageSize=1", timeout=25)
    if history.status_code == 404:
        print("HISTORY MISSING: no published daily history", flush=True)
    else:
        check(history, "HISTORY READ")
        print("HISTORY READ OK: document_present=" + str(bool(history.json().get("documents"))), flush=True)
    print("FIRESTORE CONNECTION TEST PASSED", flush=True)
    if not dashboard_present:
        print("PUBLISHER DATA CHECK: MISSING. Connection is healthy; investigate cloud paper session publisher.", flush=True)
    else:
        print("PUBLISHER DATA CHECK: PRESENT. Next check deployed client Firestore rules and Firebase UID.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FIRESTORE CONNECTION TEST FAILED: " + type(exc).__name__ + ": " + str(exc)[:180], file=sys.stderr)
        sys.exit(1)
