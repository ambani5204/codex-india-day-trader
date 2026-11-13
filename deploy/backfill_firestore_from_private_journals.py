"""Publish verified archived paper-session metrics to Firestore; no fake trades."""
from __future__ import annotations
import base64
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
from deploy.private_journal_sync import call, DEST
from deploy.firebase_live_publisher import JOURNALS, snapshot, publish
from india_trader.core import IST

def main():
    token = os.environ.get("JOURNAL_REPO_TOKEN", "")
    if not token:
        raise RuntimeError("JOURNAL_REPO_TOKEN missing")
    repo = call("/repos/" + DEST, token)
    if repo.get("private") is not True:
        raise RuntimeError("Journal source is not private")
    folders = call("/repos/" + DEST + "/contents/journals", token)
    dates = sorted((x["name"] for x in folders if x.get("type") == "dir"
                    and len(x["name"]) == 10 and x["name"][4] == "-" and x["name"][7] == "-"), reverse=True)
    if not dates:
        raise RuntimeError("No archived paper trading dates")
    day = dates[0]
    dt.date.fromisoformat(day)
    items = call("/repos/" + DEST + "/contents/journals/" + day, token)
    files = [x for x in items if x.get("type") == "file" and x["name"].endswith(".jsonl")
             and x["name"].startswith(day + "_") and x.get("size", 0) < 5_000_000]
    if not files:
        raise RuntimeError("No valid archived journals for " + day)
    JOURNALS.mkdir(parents=True, exist_ok=True)
    markets = set()
    for item in files:
        name = item["name"]
        market = name[len(day)+1:].split("_", 1)[0]
        if market not in ("NIFTY", "SENSEX"):
            continue
        response = call("/repos/" + DEST + "/contents/journals/" + day + "/" + urllib.parse.quote(name), token)
        raw = base64.b64decode(response["content"])
        if not raw.strip():
            continue
        # Validate all lines before allowing the file into the snapshot.
        for line in raw.splitlines():
            if line.strip() and not isinstance(json.loads(line), dict):
                raise RuntimeError("Malformed archived journal")
        (JOURNALS / name).write_bytes(raw)
        markets.add(market)
    if not markets:
        raise RuntimeError("No verified NIFTY/SENSEX journals")
    market = sorted(markets)[0]
    data = snapshot(market, "ARCHIVED_SESSION", "private-journal-backfill", day=day)
    if not (data["closed_trades"] or data["signals_count"] or data["entry_event_count"]):
        raise RuntimeError("Archive contains no trade or signal events; refusing empty snapshot")
    # Avoid overwriting an active, newer dashboard.
    from google.auth.transport.requests import AuthorizedSession
    import google.auth
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    url = "https://firestore.googleapis.com/v1/projects/" + os.environ["FIREBASE_PROJECT_ID"] + "/databases/(default)/documents/paper_dashboard/latest"
    response = session.get(url, timeout=25)
    if response.status_code not in (200, 404):
        raise RuntimeError("Unable to inspect existing dashboard: HTTP " + str(response.status_code))
    if response.status_code == 200:
        existing_day = response.json().get("fields", {}).get("date_ist", {}).get("stringValue", "")
        if existing_day >= day:
            print("Existing dashboard is as recent or newer; preserving it")
            return
    publish(data)
    print("VERIFIED ARCHIVE PUBLISHED: date=" + day + " market=" + market +
          " closed_trades=" + str(data["closed_trades"]) + " signals=" + str(data["signals_count"]), flush=True)

if __name__ == "__main__":
    main()
