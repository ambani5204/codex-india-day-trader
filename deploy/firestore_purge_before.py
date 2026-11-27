"""Owner-requested Firestore purge of paper data dated BEFORE a cutoff (CHG-20261127-1205).

Owner decision 2026-11-27 11:57 IST: permanently delete Firestore paper history
before 2026-11-27, no backup. This tool:

* discovers every root collection (``listCollectionIds``), pages all documents;
* dates a document by ``date_ist`` / ``report_date`` / ``date`` fields, else by a
  ``YYYY-MM-DD`` prefix in its document ID; UNDATED documents are never deleted;
* deletes only documents strictly before ``--cutoff`` (and their subcollection
  documents, recursively), never anything on/after the cutoff;
* refuses a cutoff later than today's IST date (cannot touch today's session);
* defaults to ``dry-run``; ``apply`` requires ``--confirm DELETE-BEFORE-<cutoff>``.

Prints aggregate counts per collection/date only, never document values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
DATE_FIELDS = ("date_ist", "report_date", "date")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PAGE_SIZE = 300
MAX_DOCS = 20000


def doc_date(name: str, fields: dict):
    for key in DATE_FIELDS:
        value = (fields.get(key) or {}).get("stringValue")
        if isinstance(value, str):
            m = DATE_RE.match(value)
            if m:
                return m.group(1)
    doc_id = name.rsplit("/", 1)[-1]
    m = DATE_RE.match(doc_id)
    return m.group(1) if m else None


def validate_cutoff(cutoff: str, today: str) -> str:
    try:
        dt.date.fromisoformat(cutoff)
    except ValueError:
        raise SystemExit("invalid --cutoff (YYYY-MM-DD required)")
    if cutoff > today:
        raise SystemExit(f"refused: cutoff {cutoff} is after today {today} (IST)")
    return cutoff


def plan(docs, cutoff):
    """docs: iterable of (collection, name, fields). Returns (delete, counts)."""
    delete, counts = [], Counter()
    for coll, name, fields in docs:
        day = doc_date(name, fields)
        if day is None:
            counts[(coll, "UNDATED_KEPT")] += 1
        elif day < cutoff:
            delete.append(name)
            counts[(coll, "DELETE " + day)] += 1
        else:
            counts[(coll, "KEPT " + day)] += 1
    return delete, counts


class Firestore:
    def __init__(self, session, project):
        self.s = session
        self.root = f"projects/{project}/databases/(default)/documents"
        self.api = "https://firestore.googleapis.com/v1/"

    def collection_ids(self, parent):
        ids, token = [], None
        while True:
            body = {"pageSize": 300}
            if token:
                body["pageToken"] = token
            r = self.s.post(self.api + parent + ":listCollectionIds", json=body, timeout=30)
            r.raise_for_status()
            p = r.json()
            ids += p.get("collectionIds", [])
            token = p.get("nextPageToken")
            if not token:
                return ids

    def documents(self, parent, coll):
        token, n = None, 0
        while True:
            params = {"pageSize": PAGE_SIZE, "showMissing": "false"}
            if token:
                params["pageToken"] = token
            r = self.s.get(self.api + parent + "/" + coll, params=params, timeout=30)
            if r.status_code == 404:
                return
            r.raise_for_status()
            p = r.json()
            for d in p.get("documents", []):
                n += 1
                if n > MAX_DOCS:
                    raise RuntimeError("document cap exceeded; refusing partial plan")
                yield d["name"], d.get("fields", {})
            token = p.get("nextPageToken")
            if not token:
                return

    def delete_recursive(self, name):
        deleted = 0
        for sub in self.collection_ids(name):
            for child, _ in list(self.documents(name, sub)):
                deleted += self.delete_recursive(child)
        r = self.s.delete(self.api + name, timeout=30)
        if r.status_code not in (200, 404):
            r.raise_for_status()
        return deleted + 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", required=True)
    ap.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
    ap.add_argument("--confirm", default="")
    a = ap.parse_args(argv)
    today = dt.datetime.now(IST).date().isoformat()
    cutoff = validate_cutoff(a.cutoff, today)
    if a.mode == "apply" and a.confirm != f"DELETE-BEFORE-{cutoff}":
        print(f"PURGE=REFUSED reason=CONFIRM_MISMATCH expected=DELETE-BEFORE-{cutoff}", flush=True)
        return 2
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET", "")
    project = os.getenv("FIREBASE_PROJECT_ID", "")
    if not raw or not project:
        print("PURGE=UNAVAILABLE reason=MISSING_CONFIGURATION", flush=True)
        return 2
    try:
        import google.oauth2.service_account
        from google.auth.transport.requests import AuthorizedSession
        cred = google.oauth2.service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=["https://www.googleapis.com/auth/datastore"])
        fs = Firestore(AuthorizedSession(cred), project)
        colls = sorted(fs.collection_ids(fs.root))
        docs = [(c, n, f) for c in colls for n, f in fs.documents(fs.root, c)]
        delete, counts = plan(docs, cutoff)
        print(f"PURGE_PLAN cutoff={cutoff} today_ist={today} collections={len(colls)} "
              f"documents={len(docs)} to_delete={len(delete)}", flush=True)
        for (coll, label), n in sorted(counts.items()):
            print(f"PURGE_PLAN_ROW collection={coll} {label} count={n}", flush=True)
        if a.mode == "dry-run":
            print("PURGE=DRY_RUN_ONLY (nothing deleted)", flush=True)
            return 0
        total = 0
        for name in delete:
            total += fs.delete_recursive(name)
        print(f"PURGE=APPLIED deleted_documents_including_subcollections={total}", flush=True)
        return 0
    except Exception as exc:
        print("PURGE=FAILED exception_type=" + type(exc).__name__, flush=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
