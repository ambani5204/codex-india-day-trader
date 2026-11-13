"""Non-trading Firestore connectivity smoke test. Writes and removes a disposable test document."""
import json
import os
import sys
import tempfile
from pathlib import Path

def main():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", "")
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET is not configured")
    credentials_data = json.loads(raw)
    assert credentials_data["type"] == "service_account", "Secret is not a service account JSON"
    assert credentials_data["project_id"] == "stock-market-c5016", "Wrong Firebase project"
    assert credentials_data["client_email"].startswith("paper-trading-publisher@"), "Wrong service account"
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credentials = service_account.Credentials.from_service_account_info(
        credentials_data, scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    url = "https://firestore.googleapis.com/v1/projects/stock-market-c5016/databases/(default)/documents/_connection_tests/github_smoke_test"
    print("Credential parsed and authenticated; testing Firestore write/read/delete", flush=True)
    try:
        response = session.patch(url, json={"fields": {"status": {"stringValue": "ok"}}}, timeout=25)
        response.raise_for_status()
        print("WRITE OK", flush=True)
        response = session.get(url, timeout=25)
        response.raise_for_status()
        assert response.json()["fields"]["status"]["stringValue"] == "ok"
        print("READ OK", flush=True)
    finally:
        response = session.delete(url, timeout=25)
        if response.status_code not in (200, 404):
            response.raise_for_status()
        print("CLEANUP OK", flush=True)
    print("FIRESTORE CONNECTION TEST PASSED", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FIRESTORE CONNECTION TEST FAILED: " + type(error).__name__ + ": " + str(error)[:240], file=sys.stderr)
        sys.exit(1)
