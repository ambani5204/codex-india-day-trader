# Phase 0 — Cloud session gate actual log cause, 2026-11-20 IST

**Audit-only source log evidence** under `CHG-20261120-0004`. This refines earlier reports which saw green GitHub Actions jobs with skipped trading-session steps. **No production code was changed.**

| GitHub Actions run | Job ID | Gate decision line (log) | GitHub job conclusion | Trading session step |
|---|---:|---|---|---|
| [44524841092](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44524841092) | 135562542070 | `Skipping outside all-strategy startup window (08:45–15:25 IST): 2026-11-19T18:02:39.451477+05:30` | success | skipped |
| [44538910622](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44538910622) | 135611688701 | `Skipping outside all-strategy startup window (08:45–15:25 IST): 2026-11-19T19:29:17.117027+05:30` | success | skipped |

**Finding:** These two runs did *not* establish a malfunctioning gate: both fired well after the configured market-start window. The gate explicitly skipped the sessions as designed; GitHub Actions considers the job successful because *the check/skip flow completed successfully*. This is normal CI semantics. Do **not** classify either as failed execution or use the green result as evidence of an active, successful market-day trading session.

**Operational data-integrity requirement:** track `SKIPPED_OUTSIDE_WINDOW` as an explicit operational outcome separate from `COMPLETE_RECONCILED`, `FAILED`, `MARKET_CLOSED` and `NO_SIGNALS`. The current notice uses `MARKET_CLOSED_OR_DUPLICATE`, which collapses different reasons. Distinguish market calendar closure, late scheduled start and deduplication in an eventual versioned session-state contract; preserve GitHub Actions `success` for a successful non-trading skip if operational state is independently recorded and visible. A run after 15:25 IST should **not** start new paper trades.

**Still unknown:** did *any* earlier Nov 19 run complete a full market session, how the private journals relate to precise GitHub Actions run IDs, whether all 12 archived sessions were reconciled in Firestore, and whether scheduler delays caused missing paper coverage. Source audit demonstrated three recorded `SESSION_SUMMARY` events across 12 archived JSONL files (not three fully reconciled sessions).

**Risk classification update:** The earlier wording “green-but-skipped workflow defect” was too broad. This investigation confirms **observability and denominator risk**, not incorrect execution by the gate. The issue remains that job-status=success cannot be used as completed-session status. Evaluate incident severity only after linking requested market schedule, actual trigger time, session lease/heartbeat and journal summary.

**Verification limits:** Actual decoded job logs viewed through GitHub connector; no local reproduction, Firestore runtime read, holiday-calendar simulation, code fix, CI change or deployment in this iteration. Rollback: leave unmerged draft PR #16 unmerged/close it. A post-merge rollback command is not yet tested, so merger gate remains blocked.
