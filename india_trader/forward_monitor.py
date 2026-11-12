"""Frozen, prospective, human-review-only NIFTY/SENSEX index strategy monitor.

This is NOT an optimizer. Four published simple ORB/EMA research hypotheses are
held fixed. Only days from 2026-11-13 onward count as new forward evidence.
Every trade is a hypothetical spot-index chart entry; the cost-adjusted
futures proxy does NOT prove tradable profitability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path

from .core import IST
from .index_intraday_backtest import _LazyHistoricalReader
from .research_optimizer import (
    _eligible, _load_sessions, _replay_subset, simple_playbook_presets,
)

FROZEN_FORWARD_START = dt.date(2026, 11, 13)
MIN_COMPLETE_SESSIONS = 40
MIN_FORWARD_TRADES_PER_PLAYBOOK = 30
MIN_COVERAGE_FRACTION = 0.80
MIN_NET_PROFIT_FACTOR = 1.10


def _serializable_policy(policy):
    return {k: list(v) if isinstance(v, tuple) else v
            for k, v in policy.items()}


def _suggestions(rows, complete_sessions):
    """Research-only questions, never a request to loosen live risk limits."""
    findings = [
        "Keep ORB and EMA rules frozen; evaluate only sessions dated from "
        "2026-11-13 onward and do not reuse previously examined dates as "
        "independent holdout evidence.",
        "Collect actual tradable-contract bid/ask, spread, margin and fills "
        "before making any real futures/options profitability claim.",
    ]
    if complete_sessions < MIN_COMPLETE_SESSIONS:
        findings.append(
            "Collect more complete post-freeze sessions. Do not select a "
            "strategy on a handful of wins."
        )
    if any(r["forward"]["trades"] < MIN_FORWARD_TRADES_PER_PLAYBOOK for r in rows):
        findings.append(
            "Low eligible-entry frequency: inspect each playbook's FIRST "
            "blocking rejection reason and check missing-data coverage. "
            "Propose specific rule changes as a new separately tested "
            "hypothesis, never silently relax this frozen monitor."
        )
    if any((r["forward"]["gross_total_r"] or 0) < 0 for r in rows):
        findings.append(
            "Directional signals lose gross R for some playbooks; investigate "
            "breakout confirmation and trend regime before target tuning or "
            "increasing lots."
        )
    if any(r["forward"]["average_fee_drag_r"] is not None and
           r["forward"]["average_fee_drag_r"] > .15 for r in rows):
        findings.append(
            "The fee proxy consumes >0.15R per eligible trade for some "
            "playbooks; re-check stop distance and executable instrument "
            "costs before considering any strategy change."
        )
    return findings


def monitor_forward_simple(start=FROZEN_FORWARD_START, end=None,
                           market="AUTO", reader=None,
                           cache_dir="trader/backtest_cache", out=None,
                           slippage_points=1.0):
    if isinstance(start, str):
        start = dt.date.fromisoformat(start)
    if start != FROZEN_FORWARD_START:
        raise ValueError("Forward start is fixed at 2026-11-13; do not shift it")
    if end is None:
        end = dt.datetime.now(IST).date() - dt.timedelta(days=1)
    if isinstance(end, str):
        end = dt.date.fromisoformat(end)
    if end >= dt.datetime.now(IST).date():
        raise ValueError("Do not use today's possibly unfinished session")
    if end < start - dt.timedelta(days=1) or (end - start).days > 730:
        raise ValueError("Forward range must cover 0..730 past days from freeze")
    if market.upper() not in ("AUTO", "NIFTY", "SENSEX", "BOTH"):
        raise ValueError("Unsupported market")
    if not math.isfinite(slippage_points) or not 0 <= slippage_points <= 10:
        raise ValueError("Invalid research-only slippage")
    market = market.upper()
    policies = simple_playbook_presets()

    # No history yet: keep an honest explicit waiting report, without
    # downloading market data or interpreting an empty sample as a loss.
    if end < start:
        rows = []
        complete_sessions = 0
        missing = {}
        expected = 0
    else:
        sessions = _load_sessions(start, end, market,
                                  reader or _LazyHistoricalReader(), cache_dir)
        expected = len(sessions)
        days = set(x["day"] for x in sessions)
        rows = []
        # One unoptimized baseline for accurate session completeness and
        # independent filter attrition. The same sessions feed all policies.
        coverage = _replay_subset(sessions, days, None, slippage_points)
        missing = coverage["excluded"]
        complete_sessions = expected - sum(missing.values())

        for policy in policies:
            base = _replay_subset(sessions, days, policy, slippage_points)
            stressed = _replay_subset(
                sessions, days, policy, max(2.0, 2 * slippage_points))
            normal = base["metrics"]
            stress = stressed["metrics"]
            enough = (complete_sessions >= MIN_COMPLETE_SESSIONS and
                      normal["trades"] >= MIN_FORWARD_TRADES_PER_PLAYBOOK)
            coverage_ok = expected > 0 and (complete_sessions / expected >=
                                            MIN_COVERAGE_FRACTION)
            proxy_pass = (enough and coverage_ok and
                          _eligible(normal, MIN_FORWARD_TRADES_PER_PLAYBOOK,
                                    profit_factor=MIN_NET_PROFIT_FACTOR) and
                          _eligible(stress, MIN_FORWARD_TRADES_PER_PLAYBOOK,
                                    profit_factor=MIN_NET_PROFIT_FACTOR))
            rows.append({
                "playbook": policy["name"],
                "frozen_settings": _serializable_policy(policy),
                "forward": normal,
                "double_slippage_stress": stress,
                "candidate_signals": base["signals"],
                "first_blocking_rejections": base["rejections"],
                "qualified_proxy_only_for_human_review": bool(proxy_pass),
            })

    qualifying = [r for r in rows if r["qualified_proxy_only_for_human_review"]]
    if end < start:
        status = "AWAITING_FIRST_FORWARD_DATE"
    elif expected == 0 or complete_sessions == 0:
        status = "NO_COMPLETE_MARKET_SESSIONS"
    elif complete_sessions / expected < MIN_COVERAGE_FRACTION:
        status = "INSUFFICIENT_MARKET_DATA_COVERAGE"
    elif qualifying:
        status = "REVIEW_PAPER_ONLY_HYPOTHESIS_NOT_DEPLOYMENT_APPROVAL"
    elif (complete_sessions < MIN_COMPLETE_SESSIONS or
          any(x["forward"]["trades"] < MIN_FORWARD_TRADES_PER_PLAYBOOK
              for x in rows)):
        status = "COLLECTING_PROSPECTIVE_EVIDENCE"
    else:
        status = "NO_FROZEN_PLAYBOOK_PASSED_FORWARD_COST_STRESS"

    proposals = _suggestions(rows, complete_sessions)
    report = {
        "kind": "FROZEN_PROSPECTIVE_INDEX_RESEARCH_HUMAN_REVIEW_ONLY",
        "status": status,
        "generated_at_ist": dt.datetime.now(IST).isoformat(),
        "forward_freeze_date": start.isoformat(),
        "through_completed_calendar_date": end.isoformat(),
        "market": market,
        "hypotheses": [p["name"] for p in policies],
        "expected_weekday_sessions": expected,
        "complete_market_sessions": complete_sessions,
        "unavailable_or_incomplete_sessions": missing,
        "coverage_pct": round(100 * complete_sessions / expected, 2)
                        if expected else None,
        "minimum_complete_market_sessions": MIN_COMPLETE_SESSIONS,
        "minimum_trades_per_hypothesis": MIN_FORWARD_TRADES_PER_PLAYBOOK,
        "minimum_coverage_fraction": MIN_COVERAGE_FRACTION,
        "minimum_fee_adjusted_profit_factor": MIN_NET_PROFIT_FACTOR,
        "cost_model": "SPOT_INDEX_PRICE_WITH_DATE_AWARE_FUTURES_CHARGES_PROXY",
        "slippage_index_points_each_side": slippage_points,
        "stress_slippage_index_points_each_side": max(
            2.0, slippage_points * 2),
        "results": rows,
        "proposed_investigations_for_human_review": proposals,
        "estimated_income_tax_inr": None,
        "actual_executable_futures_or_options_pnl_inr": None,
        "approved_strategy_changes": [],
        "requires_human_approval": True,
        "safe_to_scale_or_deploy": False,
        "warning": ("Frozen four-hypothesis prospective research only. "
                    "Daily monitoring reuses the SAME dates as they accumulate, "
                    "not fresh independent tests each night. A candidate passing "
                    "is ONLY a suggestion for human review, never proof of an "
                    "after-tax tradable edge, and never authorizes order execution, "
                    "option/credit spread purchases, capital scaling, or changes "
                    "to the current paper runner."),
    }
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Freeze ORB/EMA and monitor newer full market days; no orders")
    parser.add_argument("--through", default=None,
                        help="Completed date (YYYY-MM-DD), never current date")
    parser.add_argument("--market", default="AUTO",
                        choices=("AUTO", "NIFTY", "SENSEX", "BOTH"))
    parser.add_argument("--cache-dir", default="trader/backtest_cache")
    parser.add_argument(
        "--out", default="trader/backtests/nightly_forward_research.json")
    parser.add_argument("--slippage-points", type=float, default=1.0)
    args = parser.parse_args(argv)
    result = monitor_forward_simple(
        end=args.through, market=args.market, cache_dir=args.cache_dir,
        out=args.out, slippage_points=args.slippage_points)
    print(json.dumps(
        {k: result[k] for k in (
            "status", "forward_freeze_date",
            "through_completed_calendar_date", "complete_market_sessions",
            "coverage_pct", "results", "proposed_investigations_for_human_review",
            "safe_to_scale_or_deploy")},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
