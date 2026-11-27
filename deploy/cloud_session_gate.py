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


def completed_run_executed_session(repo: str, run_id: int, token: str) -> bool:
    """A green gate-only workflow must never reserve the whole market day."""
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cloud-Paper-Session-Dedup",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        jobs = json.loads(response.read()).get("jobs", [])
    for job in jobs:
        for step in job.get("steps", []):
            if step.get("name", "").startswith("Run live option-quote CE/PE paper session"):
                return step.get("conclusion") in ("success", "failure", "cancelled")
    return False


def prior_run_blocks_new_session(run: dict, repo: str, token: str) -> bool:
    """No retry after a real worker attempt until durable resume is verified.

    Earlier attempts that never ran the market-session step may be retried.
    A failed/cancelled market worker can have durable private paper fills; a
    green GitHub workflow is likewise not evidence of terminal reconciliation.
    """
    if run.get("status") != "completed":
        return True
    return completed_run_executed_session(repo, int(run["id"]), token)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    token = os.environ["GITHUB_TOKEN"]
    now = dt.datetime.now(IST)
    market_window = now.weekday() < 5 and dt.time(8, 45) <= now.time() < dt.time(15, 25)
    if not market_window:
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("should_run=false\n")
        print(f"Skipping outside all-strategy startup window (08:45–15:25 IST): {now.isoformat()}")
        return
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
        # Dedup against runs of THIS workflow only (works for both the single-job
        # and the morning/afternoon split, whatever each is named).
        this_workflow = os.environ.get("GITHUB_WORKFLOW", "Cloud CE-PE live paper trading (NO REAL ORDERS)")
        if run.get("name") != this_workflow:
            continue
        if int(run["id"]) == run_id:
            continue
        created = dt.datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(IST)
        if created.date() != now.date() or not dt.time(8, 45) <= created.time() < dt.time(15, 25):
            continue
        # Pre-market launches must also block later retry launches.
        # An attempted session may have persisted fills even when GitHub reports
        # failure/cancellation; do NOT retry until durable recovery is proven.
        if int(run["id"]) >= run_id:
            continue
        if prior_run_blocks_new_session(run, repo, token):
            competing.append(run["id"])
    should_run = not competing
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"should_run={'true' if should_run else 'false'}\n")
    print("Paper session allowed" if should_run else "Skipping duplicate market-day run")


if __name__ == "__main__":
    main()
