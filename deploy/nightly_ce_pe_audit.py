"""Nightly analysis of PUBLIC-SAFE CE/PE session aggregates.

Does not claim to explain individual trades: detailed journal analysis requires
private storage. Uses only artifacts from the cloud CE/PE workflow.
"""
from __future__ import annotations
import datetime as dt
import io
import json
import os
from pathlib import Path
import urllib.request
import zipfile

from india_trader.core import IST

REPO = os.environ.get("GITHUB_REPOSITORY", "")
API = "https://api.github.com"
OUT = Path("trader/nightly_ce_pe_audit.md")


def request(path: str, *, binary: bool = False):
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not REPO:
        raise RuntimeError("GitHub token and repository are required")
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CE-PE-Aggregate-Audit",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    return data if binary else json.loads(data)


def analyze(summary: dict) -> str:
    day = summary["date_ist"]
    counts = summary.get("event_counts", {})
    trades = int(summary.get("closed_trades", 0))
    net = float(summary.get("net_pnl_inr_estimated", 0))
    signals = int(counts.get("INDEX_SIGNAL", 0))
    rejections = int(counts.get("SIGNAL_REJECTED", 0))
    errors = int(counts.get("MARKET_DATA_ERROR", 0))
    lines = [
        f"# CE/PE paper trading audit — {day}",
        "",
        f"Market: {summary.get('market', 'UNKNOWN')}",
        f"Session status: {summary.get('status', 'UNKNOWN')}",
        f"Paper trades closed: {trades}; estimated net P&L: ₹{net:.2f}",
        f"Signals: {signals}; rejected signals: {rejections}; data errors: {errors}",
        "",
        "## Diagnostics",
    ]
    if summary.get("status") != "COMPLETE":
        lines.append("- Session incomplete or failed; do not treat missing trades as valid no-trade evidence.")
    if errors:
        lines.append("- Market-data errors occurred. Review private runtime logs before assessing strategy quality.")
    if rejections:
        lines.append("- Some signals were rejected by eligibility, liquidity, or risk checks; aggregate counts cannot identify which guard dominated.")
    if not signals:
        lines.append("- No qualifying index signals were recorded; this alone does not prove the strategy is good or bad.")
    if trades and net < 0:
        lines.append("- Estimated net losses occurred; inspect entry/exit quote snapshots in private journals to attribute slippage, spread, timing and stop placement.")
    if trades and net >= 0:
        lines.append("- Positive paper result is not evidence of a repeatable edge or achievable broker fills.")
    if not trades:
        lines.append("- No closed paper trades. Check whether there were signals, rejections or incomplete sessions.")
    lines += [
        "",
        "## Exit categories",
        *[f"- {k}: {v}" for k, v in sorted(summary.get("exit_reason_counts", {}).items())],
        "",
        "## Research guardrails",
        "- Paper-only: no exchange executions or live orders.",
        "- Public repository: this report deliberately contains no individual option quotes, trades, strikes or credentials.",
        "- Individual-trade failure attribution requires a private journal store and a separate secure analysis job.",
        "- Do not automatically alter the strategy or increase position size based on this report.",
    ]
    return "\n".join(lines) + "\n"


def main():
    today = dt.datetime.now(IST).date().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        runs = request(f"/repos/{REPO}/actions/workflows/cloud-ce-pe-paper.yml/runs?per_page=15")
        summary = None
        for run in runs.get("workflow_runs", []):
            if run.get("status") != "completed":
                continue
            artifacts = request(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts")
            for artifact in artifacts.get("artifacts", []):
                if not artifact["name"].startswith("public-safe-ce-pe-summary-") or artifact.get("expired"):
                    continue
                archive = request(f"/repos/{REPO}/actions/artifacts/{artifact['id']}/zip", binary=True)
                with zipfile.ZipFile(io.BytesIO(archive)) as z:
                    names = [n for n in z.namelist() if n.endswith("cloud_paper_summary.json")]
                    if not names:
                        continue
                    candidate = json.loads(z.read(names[0]))
                if candidate.get("date_ist") == today:
                    summary = candidate
                    break
            if summary:
                break
        if summary:
            report = analyze(summary)
        else:
            report = (f"# CE/PE paper trading audit — {today}\n\n"
                      "No cloud paper session aggregate found for today. "
                      "This is **missing evidence**, not a zero-trade or successful session.\n")
    except Exception as exc:
        # Do not leak API responses or access tokens to a public artifact.
        report = (f"# CE/PE paper trading audit — {today}\n\n"
                  f"Audit retrieval failed ({type(exc).__name__}). "
                  "No conclusions can be drawn from unavailable session data.\n")
    OUT.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
