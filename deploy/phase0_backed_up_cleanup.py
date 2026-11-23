"""One-time, backed-up Firestore cleanup of ambiguous paper history dates.

Runs only inside the private repository's GitHub Actions with service-account access.
Preserves all private JSONL archives. Does not touch broker orders.
"""
import hashlib
import json
import os
import pathlib
import sys

from deploy.phase0_firestore_journal_reconcile import get_history, duplicate_history_keys
from deploy.nightly_strategy_evaluation import unpack

PROJECT = "stock-market-c5016"
COLLECTIONS = ("paper_history", "paper_dashboard", "paper_evaluations")
BACKUP = pathlib.Path("phase0_cleanup_backup.json")
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
TARGET_DATE = "2026-11-14"


def client():
    import google.oauth2.service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET"])
    if info.get("project_id") != PROJECT:
        raise RuntimeError("Unexpected service-account project")
    credentials = google.oauth2.service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/datastore"])
    return AuthorizedSession(credentials)


def list_docs(session, collection):
    docs, page = [], None
    while True:
        params = {"pageSize": 100}
        if page:
            params["pageToken"] = page
        resp = session.get(f"{BASE}/{collection}", params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        docs.extend(body.get("documents", []))
        page = body.get("nextPageToken")
        if not page:
            return docs


def doc_date(doc):
    fields = doc.get("fields", {})
    for key in ("date_ist", "report_date", "date"):
        if key in fields:
            value = unpack(fields[key])
            if isinstance(value, str) and len(value) >= 10:
                return value[:10]
    # Date-only evaluation documents may encode their date as the document ID.
    if doc["name"].split("/")[-2] == "paper_evaluations":
        name = doc["name"].split("/")[-1]
        if len(name) == 10 and name[4] == "-" and name[7] == "-":
            return name
    return None


def plan():
    session = client()
    history = get_history()
    duplicates = duplicate_history_keys(
        [r for r in history if r.get("market") in ("NIFTY", "SENSEX") and r.get("date_ist")])
    dates = {str(date) for date, _ in duplicates} | {TARGET_DATE}
    if not duplicates:
        print("CLEANUP_ABORT reason=NO_DUPLICATES", flush=True)
        return 4
    if len(dates) > 3:
        print("CLEANUP_ABORT reason=TOO_MANY_DATES", flush=True)
        return 4
    records = {}
    for collection in COLLECTIONS:
        records[collection] = [d for d in list_docs(session, collection)
                               if doc_date(d) in dates]
    if not records["paper_history"]:
        print("CLEANUP_ABORT reason=NO_HISTORY_TO_REMOVE", flush=True)
        return 4
    payload = {"project": PROJECT, "dates": sorted(dates), "records": records}
    BACKUP.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(BACKUP.read_bytes()).hexdigest()
    pathlib.Path("phase0_cleanup_digest.txt").write_text(digest)
    print("CLEANUP_BACKUP_READY dates=" + str(len(dates)) +
          " documents=" + str(sum(map(len, records.values()))), flush=True)
    return 0


def apply():
    """Fail closed: no DELETE permitted under the current Phase 0 policy.

    Re-enabling cleanup requires a separately reviewed change with explicit
    authorization, verified offsite backup, tested restore, and per-document
    preconditions. This function intentionally does not load credentials.
    """
    print("CLEANUP_ABORT reason=DESTRUCTIVE_APPLY_DISABLED", flush=True)
    return 4


if __name__ == "__main__":
    sys.exit(plan() if sys.argv[1:] == ["plan"] else apply() if sys.argv[1:] == ["apply"] else 2)
