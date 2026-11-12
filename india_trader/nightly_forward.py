"""Unattended, NO-ORDER workflow entrypoint with explicit failure artifact.

Never substitutes fake market data or silently reports success on missing
or rejected Upstox Analytics credentials. Secrets are not printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from .core import IST
from .forward_monitor import monitor_forward_simple


def run_nightly(out, token=None, through=None):
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = token if token is not None else os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        result = {
            "kind": "FORWARD_RESEARCH_UNAVAILABLE_NO_MARKET_DATA",
            "status": "NOT_RUN_MISSING_UPSTOX_ANALYTICS_TOKEN",
            "reason": ("Set the repository Actions secret UPSTOX_ACCESS_TOKEN "
                       "to a read-only, 1-year Upstox Analytics Token. "
                       "The nightly job cannot access the phone's private token."),
            "safe_to_scale_or_deploy": False,
        }
        success = False
    else:
        try:
            result = monitor_forward_simple(
                end=through, out=out, slippage_points=1.0)
            success = True
        except Exception as exc:
            # No exception text; Upstox HTTP errors might disclose URLs
            # or other sensitive data. A failed run is never treated as 0 P&L.
            result = {
                "kind": "FORWARD_RESEARCH_UNAVAILABLE_NO_MARKET_DATA",
                "status": "DATA_UNAVAILABLE_OR_AUTHENTICATION_FAILED",
                "error_class": type(exc).__name__,
                "reason": ("Could not retrieve/validate actual Upstox index "
                           "candles. Check Analytics Token authorization, "
                           "rate limits and historical data coverage in a "
                           "private environment; no results are inferred."),
                "safe_to_scale_or_deploy": False,
            }
            success = False
    if not success:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [
            "## Scheduled frozen ORB / EMA strategy research",
            "",
            f"Status: **{result['status']}**",
            "",
            "Automatic orders, paper strategy mutations and lot-size increases: **NO**",
            "",
        ]
        if success:
            lines.extend([
                "Monitoring begins: **2026-11-13** (no earlier inspected days)",
                f"Complete market sessions: **{result['complete_market_sessions']}**",
                f"Expected scheduled sessions: **{result['expected_weekday_sessions']}**",
                f"Data coverage: **{result['coverage_pct']}%**",
                "P&L source: **hypothetical index futures-fee proxy, not real trades**",
            ])
        else:
            lines.append(result["reason"])
        with open(summary, "a", encoding="utf-8") as fp:
            fp.write("\n".join(lines) + "\n")
    print("Nightly frozen-research status:", result["status"], flush=True)
    if success:
        print("Complete sessions:", result["complete_market_sessions"], flush=True)
    return result, 0 if success else 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Research only: never submits orders or deploys changes")
    parser.add_argument("--out", default="trader/backtests/nightly_forward_research.json")
    parser.add_argument("--through", default=None,
                        help="Last completed date; default yesterday IST")
    args = parser.parse_args(argv)
    _, code = run_nightly(args.out, through=args.through)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
