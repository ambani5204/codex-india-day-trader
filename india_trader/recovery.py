"""Session recovery classification (Phase 6).

On startup a worker must decide what an existing journal means before doing
anything. This classifies the journal's events into one state. Only a PAUSED
handoff (the two-job split) may auto-resume; a crash or an unresolved position
must NOT be silently retried — it needs reconciliation first. This encodes the
gate's "durable resume verified" precondition as an inspectable function.

Pure: reads events (list of dicts), returns a verdict. No I/O, no network.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

CLEAN = "CLEAN"                              # terminal SESSION_SUMMARY present
NO_SESSION = "NO_SESSION"                    # nothing started
PAUSED_RESUMABLE = "PAUSED_RESUMABLE"        # split handoff; afternoon may resume
UNRESOLVED_NEEDS_RECONCILE = "UNRESOLVED_NEEDS_RECONCILE"
CRASHED_NO_TERMINAL = "CRASHED_NO_TERMINAL"

AUTO_RESUMABLE = {PAUSED_RESUMABLE}
MUST_NOT_RETRY = {UNRESOLVED_NEEDS_RECONCILE, CRASHED_NO_TERMINAL}


@dataclass
class Recovery:
    state: str
    can_auto_resume: bool
    reason: str


def classify(events: Sequence[dict]) -> Recovery:
    evs: List[dict] = [e for e in events if isinstance(e, dict) and e.get("event")]
    if not evs:
        return Recovery(NO_SESSION, False, "no events")
    if evs[0].get("event") != "SESSION_START":
        # Malformed: a non-start first event means the ledger is untrustworthy.
        return Recovery(UNRESOLVED_NEEDS_RECONCILE, False,
                        "first event is not SESSION_START")
    kinds = [e.get("event") for e in evs]
    last = kinds[-1]
    has_unresolved = "UNRESOLVED_POSITION" in kinds
    if last == "SESSION_SUMMARY" and not has_unresolved:
        return Recovery(CLEAN, False, "session summarised and reconciled")
    if has_unresolved:
        return Recovery(UNRESOLVED_NEEDS_RECONCILE, False,
                        "unresolved position in ledger; reconcile before any retry")
    if last == "SESSION_PAUSED":
        return Recovery(PAUSED_RESUMABLE, True, "two-job split handoff; afternoon may resume")
    return Recovery(CRASHED_NO_TERMINAL, False,
                    "started but no terminal event; treat as crash, reconcile first")
