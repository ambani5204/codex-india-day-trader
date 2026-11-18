"""Restore today's verified private paper journals before any worker starts.

Fail closed if private archive cannot be read. Restored files are immutable
historical sessions; the new worker creates a new session ID and journal.
"""
from __future__ import annotations
import base64
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.error
from deploy.private_journal_sync import call, DEST, SOURCE
from india_trader.core import IST

def restore(day=None, token=None):
    day = day or dt.datetime.now(IST).date().isoformat()
    dt.date.fromisoformat(day)
    token = token or os.environ["JOURNAL_REPO_TOKEN"]
    repo = call("/repos/" + DEST, token)
    if repo.get("private") is not True or repo.get("full_name", "").lower() != DEST.lower():
        raise RuntimeError("Private journal archive verification failed")
    try:
        listing = call("/repos/" + DEST + "/contents/journals/" + day, token)
    except Exception as exc:
        # A fresh market day has no archive; only a genuine 404 is acceptable.
        if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
            return 0
        raise
    if not isinstance(listing, list):
        raise RuntimeError("Invalid archive listing")
    SOURCE.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in listing:
        name = item.get("name", "")
        if not (item.get("type") == "file" and name.startswith(day + "_")
                and name.endswith(".jsonl") and 0 < item.get("size", 0) < 5_000_000
                and all(c.isalnum() or c in "._-" for c in name)):
            continue
        if not (name.startswith(day + "_NIFTY_") or name.startswith(day + "_SENSEX_")):
            continue
        response = call("/repos/" + DEST + "/contents/journals/" + day + "/" +
                        urllib.parse.quote(name), token)
        # GitHub Contents API wraps Base64 at line boundaries. Strip only
        # ASCII whitespace; strict validation still rejects corrupt payloads.
        encoded = response["content"]
        if response.get("encoding", "base64") != "base64" or not isinstance(encoded, str):
            raise RuntimeError("Archived journal has invalid content encoding " + name)
        raw = base64.b64decode("".join(encoded.split()), validate=True)
        if not raw.strip() or any(not isinstance(json.loads(line), dict)
                                  for line in raw.splitlines() if line.strip()):
            raise RuntimeError("Malformed archived journal " + name)
        # A verified start-only journal is an interrupted worker with no
        # recorded signal, position, or trade. Keep the immutable original in
        # the private archive, but do not rehydrate it as an active session.
        # Any additional event remains fail-closed for manual reconciliation.
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if (len(events) == 1 and events[0].get("event") == "SESSION_START"
                and events[0].get("market") in ("NIFTY", "SENSEX")
                and name.startswith(day + "_" + events[0]["market"] + "_")
                and events[0].get("session") == name.removesuffix(".jsonl")):
            print("ARCHIVED_START_ONLY_INTERRUPTED=" + name, flush=True)
            continue
        path = SOURCE / name
        if path.exists():
            if path.read_bytes() != raw:
                raise RuntimeError("Existing journal differs from private archive " + name)
        else:
            path.write_bytes(raw)
        count += 1
    print("PRIVATE_JOURNALS_RESTORED=" + str(count), flush=True)
    return count

if __name__ == "__main__":
    restore()
