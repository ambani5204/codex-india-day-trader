"""Upload CE/PE paper JSONL journals to a separate PRIVATE GitHub repository.

Only journal files are uploaded. Never upload broker tokens, configs, logs or
SQLite databases. The destination must be private and explicitly named.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from india_trader.core import IST

DEST = "ambani5204/codex-trading-journals"
SOURCE = Path("trader/paper_upstox")
API = "https://api.github.com"


def call(path, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "CE-PE-Private-Journal-Sync",
    })
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("JOURNAL_REPO_TOKEN")
    if not token:
        raise RuntimeError("JOURNAL_REPO_TOKEN is not configured")
    repo = call("/repos/" + DEST, token)
    if repo.get("full_name", "").lower() != DEST.lower() or repo.get("private") is not True:
        raise RuntimeError("Destination is missing or not private: upload refused")
    if args.verify_only:
        probe_path = "/repos/" + DEST + "/contents/.journal-sync-write-probe.json"
        existing_sha = None
        try:
            existing_sha = call(probe_path, token).get("sha")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        payload = {
            "message": "Verify scoped private journal write access",
            "content": base64.b64encode(b'{"status":"private-write-ok"}\\n').decode("ascii"),
        }
        if existing_sha:
            payload["sha"] = existing_sha
        call(probe_path, token, "PUT", payload)
        print("Private destination verified; token can WRITE safely.")
        return
    today = dt.datetime.now(IST).date().isoformat()
    files = sorted(SOURCE.glob(today + "_*.jsonl"))
    if not files:
        raise RuntimeError("No paper journals for today; no upload performed")
    saved = 0
    for file in files:
        if not file.is_file() or file.stat().st_size > 5_000_000:
            raise RuntimeError("Journal missing or exceeds safe upload size")
        # Prevent unexpected paths or filenames escaping the private journal folder.
        if not all(c.isalnum() or c in "._-" for c in file.name):
            raise RuntimeError("Unsafe journal filename")
        dest = "journals/" + today + "/" + file.name
        encoded = urllib.parse.quote(dest, safe="/")
        existing_sha = None
        try:
            existing = call("/repos/" + DEST + "/contents/" + encoded, token)
            existing_sha = existing.get("sha")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        payload = {
            "message": "Archive private CE/PE paper journal " + file.name,
            "content": base64.b64encode(file.read_bytes()).decode("ascii"),
        }
        if existing_sha:
            payload["sha"] = existing_sha
        call("/repos/" + DEST + "/contents/" + encoded, token, "PUT", payload)
        saved += 1
    print("Uploaded", saved, "journal file(s) to verified private repository")


if __name__ == "__main__":
    main()
