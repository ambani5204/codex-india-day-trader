"""Periodically archive append-only paper journals to the verified PRIVATE repository.

Runs as a separate workflow sidecar. Failures are visible; never writes to
Firestore, places orders, or deletes a journal. The final workflow archive
remains a separate safety net.
"""
from __future__ import annotations
import datetime as dt
import os
from pathlib import Path
import signal
import time
from india_trader.core import IST
from deploy import private_journal_sync

STOP = False

def request_stop(*_args):
    global STOP
    STOP = True

def main(interval=60):
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    if not os.environ.get("JOURNAL_REPO_TOKEN"):
        raise RuntimeError("Checkpoint token missing")
    # Verify private destination before starting any write.
    token = os.environ["JOURNAL_REPO_TOKEN"]
    repo = private_journal_sync.call("/repos/" + private_journal_sync.DEST, token)
    if repo.get("private") is not True or repo.get("full_name", "").lower() != private_journal_sync.DEST.lower():
        raise RuntimeError("Refusing non-private journal checkpoint destination")
    while not STOP:
        today = dt.datetime.now(IST).date().isoformat()
        files = list(Path("trader/paper_upstox").glob(today + "_*.jsonl"))
        if files:
            try:
                private_journal_sync.main()
                print("Private journal checkpoint completed", flush=True)
            except Exception as exc:
                print("::warning::Private journal checkpoint failed: " + type(exc).__name__, flush=True)
        for _ in range(interval):
            if STOP:
                break
            time.sleep(1)

if __name__ == "__main__":
    main()
