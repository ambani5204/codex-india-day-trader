# Phase 1 preparation — NIFTY-first evidence and UI contract (NOT ACTIVATED)

Status: **PREPARATION ONLY**. Master Prompt v2 §17 Phase 0 remains OPEN. This is not `docs/PLAN.md`, is not a Phase 1 start, and authorizes no production merge, deployment, broker order, or live paper workflow change.

## Exit dependencies (all must be verified first)
1. Real credentialed GET-only Firestore duplicate market/date history groups reconciled by session identity, including restart/termination lineage. Never collapse distinct sessions into a latest-snapshot estimate.
2. 2026-11-14 orphan evaluation #20 provenance established from underlying source and trading calendar; preserve records.
3. Private JSONL↔Firestore session, signal, closed-trade, fee, after-cost P&L coverage totals reconciled without private data in public CI.
4. Android LIVE/OVERALL actual-source contract, null/stale/skipped status, signed APK/device screenshots accepted.
5. Workflow start/end and rollback rehearsal verified with evidence and tracker §17 signed-off. Phase 1 starts only after these gates.

## Proposed isolated implementation slices (do not activate)
**Slice A — typed NIFTY-first read model.** Separate `PAPER_SIMULATION` from `PROXY_RESEARCH`. Every KPI carries `source`, `as_of_ist`, `coverage`, `session_state`, and `verification_state`. Missing or partial financial coverage => P&L unavailable, never zero. Duplicate/unknown session identity => blocked, never silently deduplicated. SENSEX follows the same contract.

**Slice B — Android visual-first contract.** Top-right workflow status details distinguish SCHEDULED, STARTING, RUNNING, COMPLETED, FAILED, CANCELLED, STALE and UNKNOWN. NIFTY-first compact cards show signals, verified closed trades, net after-cost paper P&L only when complete, and drawdown only when calculable from actual verified trade sequence. Strategy P&L table and actual-data charts must show clear unavailable/partial states, never placeholder trades or manufactured charts. Use private-journals draft PR #4 visual-first skill and `android-app/PHASE0_UI_ACCEPTANCE.md`; PR #5 remains unmerged. Screenshots, signed APK, device and rollback tests required before release.

**Slice C — historical research separation.** Research can ingest validated index OHLC only as `PROXY_RESEARCH`; index points cannot be presented as options premiums or net options P&L. Real options research needs timestamped CE/PE bid/ask, lot size, expiry, instrument mapping, brokerage, exchange fees, taxes, slippage, missing-quote policy and walk-forward/out-of-sample coverage. Report no win-rate or profitability claim until evidence is available.

## Proposed offline acceptance matrix
- Two same-market/date rows with different sessions => BLOCKED pending reconciliation, not merged into one session.
- Missing session ID, malformed market/date, partial P&L coverage => explicit UNVERIFIED/UNAVAILABLE.
- Missing/stale API data, skipped signals, cancelled workflow => distinct UI states.
- Index-only research => PROXY RESEARCH label and no options P&L.
- No network, secrets, broker orders or production Firestore writes in offline tests.

## Change control
Preparation branch only. After Phase 0 exit, review and author formal `docs/PLAN.md` as a separate gated action. Rollback of this preparatory change: close draft PR/delete branch. Production rollback remains untested; this document is not a substitute.
