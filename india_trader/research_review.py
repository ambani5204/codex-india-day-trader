"""Render and (optionally) upsert a HUMAN-REVIEW GitHub Issue.

Reads ONLY a completed aggregate forward research report, never credentials.
No source-code writes, no merges, no PR approvals, and no broker orders.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

TITLE = "[Research] Frozen ORB / EMA forward evidence — human review only"
MARKER = "<!-- codex-index-research-review-v1 -->"
KIND = "FROZEN_PROSPECTIVE_INDEX_RESEARCH_HUMAN_REVIEW_ONLY"


def _fmt(value):
    return "N/A" if value is None else str(value)


def render_review_markdown(report, run_url=None):
    if report.get("kind") != KIND:
        raise ValueError("Only a valid frozen prospective research report may create a review")
    status = str(report["status"])
    if not status or status.startswith(("NOT_RUN", "DATA_UNAVAILABLE")):
        raise ValueError("No independent market observations were validated")
    text = [
        MARKER,
        "# Frozen opening-range and EMA research — review requested",
        "",
        "**Status:** `" + status + "`",
        "",
        "**This issue is NOT approval to trade, change code or increase volume.**",
        "",
        f"Freeze date: **{report['forward_freeze_date']}** (previously inspected dates excluded).  "
        f"Last completed calendar date requested: **{report['through_completed_calendar_date']}**.",
        "",
        f"Complete market sessions: **{report['complete_market_sessions']}** "
        f"out of {report['expected_weekday_sessions']} scheduled weekday sessions; "
        f"data coverage **{_fmt(report['coverage_pct'])}%**.",
        "",
        "### Frozen hypotheses, futures-cost proxy only",
        "",
        "| Playbook | Forward trades | Net R | Net PF | 2x-slippage net R | Review gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report.get("results", []):
        m = row["forward"]
        stress = row["double_slippage_stress"]
        flag = ("Candidate for human review ONLY" if
                row["qualified_proxy_only_for_human_review"] else
                "Not qualified")
        text.append(
            f"| {row['playbook']} | {m['trades']} | "
            f"{_fmt(m['net_total_r'])} | {_fmt(m['net_profit_factor'])} | "
            f"{_fmt(stress['net_total_r'])} | {flag} |"
        )
    text += ["", "### First observed rejection reason by candidate", ""]
    for row in report.get("results", []):
        reasons = sorted(row.get("first_blocking_rejections", {}).items(),
                         key=lambda pair: (-pair[1], pair[0]))[:5]
        summary = "; ".join(f"`{name}`: {n}" for name, n in reasons)
        text.append(f"- **{row['playbook']}**: {summary or 'No recorded rejections'}")
    text += ["", "### Proposed investigations (NO automatic strategy changes)", ""]
    for suggestion in report.get("proposed_investigations_for_human_review", []):
        text.append("- " + str(suggestion))
    text += [
        "",
        "### Required before any deployment or higher lot size",
        "",
        "- Enough fresh, independent market sessions and qualified trades",
        "- Positive fee-adjusted and stressed results with controlled drawdown",
        "- Historical tradable-futures/options contract quotes and realistic fills",
        "- Separate human-approved code review and continued forward paper validation",
        "",
        "A passing chart-only futures-cost **proxy** does not validate executable "
        "futures/option profit or income taxes. Nothing in this issue activates live trades.",
        "",
        "**Approval process:** comment with the exact research hypothesis to investigate. "
        "The system will **not** interpret a comment as authorization to modify the "
        "active paper trader or send an order.",
    ]
    if run_url:
        if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/actions/runs/\d+",
                            run_url):
            raise ValueError("Invalid GitHub Actions run URL")
        text += ["", "Research run and downloadable artifacts: " + run_url]
    text += ["", "This issue is refreshed on Monday scheduled runs, or on manual dispatch."]
    return "\n".join(text) + "\n"


def _api_request(token, path, method="GET", body=None):
    if not path.startswith("/repos/"):
        raise ValueError("Disallowed GitHub API path")
    data = (json.dumps(body).encode("utf-8") if body is not None else None)
    req = urllib.request.Request(
        "https://api.github.com" + path,
        data=data, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codex-index-research-human-review",
            **({"Content-Type": "application/json"} if body is not None else {}),
        })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def upsert_review_issue(report, repo, token, run_url=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        raise ValueError("Untrusted GITHUB_REPOSITORY identifier")
    if not token:
        raise ValueError("GITHUB_TOKEN required for issue write")
    body = render_review_markdown(report, run_url=run_url)
    root = "/repos/" + repo + "/issues"
    # Never create duplicates if an issue page was truncated.
    existing = None
    for page in range(1, 6):
        page_items = _api_request(token, root + f"?state=open&per_page=100&page={page}")
        for item in page_items:
            if (item.get("title") == TITLE and
                MARKER in item.get("body", "") and
                "pull_request" not in item):
                existing = item
                break
        if existing or len(page_items) < 100:
            break
    else:
        raise RuntimeError("Too many issues to check safely; refusing duplicate creation")
    if existing:
        issue = _api_request(token, root + "/" + str(existing["number"]),
                             method="PATCH", body={"body": body})
        action = "updated"
    else:
        issue = _api_request(token, root, method="POST",
                             body={"title": TITLE, "body": body})
        action = "created"
    return {"action": action, "number": issue["number"],
            "url": issue["html_url"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="Research-only review issue; no trading")
    p.add_argument("--report", required=True)
    p.add_argument("--markdown-out", default=None)
    p.add_argument("--publish", action="store_true")
    args = p.parse_args(argv)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = (f"https://github.com/{repository}/actions/runs/{run_id}"
               if repository and run_id else None)
    rendered = render_review_markdown(report, run_url=run_url)
    if args.markdown_out:
        path = Path(args.markdown_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    if args.publish:
        result = upsert_review_issue(
            report, repository, os.environ.get("GITHUB_TOKEN", ""),
            run_url=run_url)
        print(f"Research review issue {result['action']}: {result['url']}")
    else:
        print("Research review prepared; no issue published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
