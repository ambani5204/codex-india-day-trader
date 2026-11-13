"""Fail-closed cloud session deduplication for retry cron triggers.

GitHub schedule events can be delayed or dropped. Multiple cron opportunities
improve chances, but only the earliest market-hours run may proceed.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    token = os.environ["GITHUB_TOKEN"]
    now = dt.datetime.now(IST)
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cloud-Paper-Session-Dedup",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        runs = json.loads(response.read()).get("workflow_runs", [])
    competing = []
    for run in runs:
        if run.get("name") != "Cloud CE-PE live paper trading (NO REAL ORDERS)":
            continue
        if int(run["id"]) == run_id:
            continue
        created = dt.datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(IST)
        if created.date() != now.date() or not dt.time(9, 15) <= created.time() < dt.time(15, 10):
            continue
        # Exclude runs created later; earlier run owns this trading day,
        # including failed runs, to prevent fabricated double sessions.
        if created < now and int(run["id"]) < run_id:
            competing.append(run["id"])
    should_run = not competing
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"should_run={'true' if should_run else 'false'}\n")
    print("Paper session allowed" if should_run else "Skipping duplicate market-day run")


if __name__ == "__main__":
    main()
