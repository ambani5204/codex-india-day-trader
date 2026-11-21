"""Offline-only Phase 1 UI evidence contract. No data fetching or trading actions.

Preparation only: not wired into production; §17 Phase 0 remains open.
"""
from __future__ import annotations

from datetime import datetime, timezone

PAPER = "PAPER_SIMULATION"
PROXY = "PROXY_RESEARCH"
WORKFLOW_STATES = frozenset({
    "SCHEDULED", "STARTING", "RUNNING", "COMPLETED",
    "FAILED", "CANCELLED", "STALE", "UNKNOWN",
})


def classify_paper_kpi(row, *, duplicate_sessions=False):
    """Return presentation status, never invent a missing/partial P&L."""
    if duplicate_sessions:
        return {"status": "BLOCKED_DUPLICATE_SESSION", "net_pnl": None}
    if not isinstance(row, dict):
        return {"status": "UNAVAILABLE", "net_pnl": None}
    if row.get("data_type") == PROXY:
        return {"status": "PROXY_RESEARCH", "net_pnl": None}
    if row.get("data_type") != PAPER or row.get("market") not in {"NIFTY", "SENSEX"}:
        return {"status": "UNVERIFIED_SOURCE", "net_pnl": None}
    closed, covered = row.get("closed_trades"), row.get("pnl_coverage")
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (closed, covered)):
        return {"status": "UNVERIFIED_COVERAGE", "net_pnl": None}
    if covered > closed or covered < closed:
        return {"status": "PARTIAL_OR_INVALID_COVERAGE", "net_pnl": None}
    net = row.get("net_pnl")
    if closed == 0:
        return {"status": "VERIFIED_NO_CLOSED_TRADES" if net is None else "INVALID_ZERO_TRADE_PNL",
                "net_pnl": None}
    if not isinstance(net, (int, float)) or isinstance(net, bool):
        return {"status": "UNVERIFIED_PNL", "net_pnl": None}
    import math
    if not math.isfinite(net):
        return {"status": "UNVERIFIED_PNL", "net_pnl": None}
    return {"status": "VERIFIED_PAPER", "net_pnl": float(net)}


def workflow_display_state(state, *, stale=False):
    if stale:
        return "STALE"
    return state if state in WORKFLOW_STATES else "UNKNOWN"
