# ALGOBANI delivery plan (Phase 1)

Status: **Phase 1 CLOSED 2026-11-27 (owner decision).** Supersedes docs/PHASE1_PREPARATION_NIFTY_FIRST.md.
Paper-only. Never claim profitability. See docs/decisions/ADR-0001 and docs/RISK_REGISTER.md.

## Phase 1 exit (per #17: "plan, milestones, ADR/assumptions, tested rollback design")
- [x] Plan — this document.
- [x] Milestones — M1–M5 below (M1 already implemented and live for Monday's full-day validation, ahead of requirement).
- [x] ADRs + assumptions — docs/decisions/ADR-0001, ADR-0002; docs/assumptions.md; the Assumptions section below.
- [x] Tested rollback design — scripts/rollback (fail-closed), ops/rollback_manifest.json, and a rehearsed end-to-end run (docs/audit/PHASE0_ROLLBACK_REHEARSAL_20261127.md). Design AND rehearsal, exceeding "design".

**Scope of this closure:** Phase 1 is the planning/design phase. Closing it means these four deliverables exist and are merged — NOT that M2–M5 execution or later phases (2–10) are done. Those remain future work, tracked below and in #17.

## Baseline reset
On 2026-11-27 the owner directed a permanent purge of all paper data before today
(journals + Firestore; executed under CHG-20261127-1205). The historical Phase 0
reconciliation blockers (#20, #21, #24) and incident #58 concerned data that no
longer exists, so they are closed as moot. Phase 0 restarts from a clean baseline of 2026-11-27 and was CLOSED on
2026-11-27 by owner decision: all engineering gates met and the 2026-11-27
session is clean and count-matched (see the Phase 0 exit status below).

## Phase 0 exit status — CLOSED 2026-11-27 (owner decision)
- [x] Inventory both repos (codex-india-day-trader + codex-trading-journals).
- [x] Fresh test baseline: 408 offline tests green on 3.10/3.11/3.12.
- [x] Firestore schema + internal read-model reconciliation: SAMPLED/MATCH, 0 anomalies, only 2026-11-27 docs remain.
- [x] Risk register (docs/RISK_REGISTER.md).
- [x] Tested SOURCE rollback rehearsal (docs/audit/PHASE0_ROLLBACK_REHEARSAL_20261127.md); manifest registered.
- [x] A clean session: 2026-11-27 NIFTY+SENSEX each closed with an end-aware SESSION_SUMMARY, no open or unresolved positions; journal↔Firestore counts MATCH.
  - **Honest caveat:** the reconciler reports `COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED` (exit 4) because a 0-trade day has no option fills to certify independently. This is the tool's built-in conservatism, not a data defect. The owner reviewed the clean summaries + matching counts and accepts this as sufficient to close Phase 0. Full after-fee options reconciliation will first be exercised when a session takes a real trade (expected from Phase 1's full-day runs).
  - Historical reconciliation items #20/#21/#24 and incident #58 are moot: their data was permanently purged on 2026-11-27 at the owner's instruction.

## Phase 1 milestones (this phase)
- **M1 — Session reliability.** Split the market-day workflow into morning + afternoon jobs so a full session finishes under the 360-min cap and always writes SESSION_SUMMARY. Add a daily 09:05 IST start path. *Exit:* one full day completes end-to-end with a reconciled summary.
- **M2 — Token/runbook.** Document and, where allowed, automate the daily Upstox token refresh; fail closed with a clear status when absent. *Exit:* a missing token produces an explicit UI/log state, never a fabricated price.
- **M3 — Typed read model (Slice A).** Every KPI carries source, as_of_ist, coverage, session_state, verification_state. Partial coverage ⇒ "unavailable", never zero. *Exit:* offline acceptance matrix passes.
- **M4 — Android visual contract (Slice B).** NIFTY-first; workflow status SCHEDULED/STARTING/RUNNING/COMPLETED/FAILED/CANCELLED/STALE/UNKNOWN; no placeholder trades or manufactured charts. *Exit:* signed APK + device screenshots.
- **M5 — ADR + rollback-first CI.** Record ADR-0002 (versioned ledger + rollback-first). *Exit:* ADR merged; rollback manifest covers every production-affecting change.

## Assumptions
- Indices (NIFTY/SENSEX) are not tradable; only CE/PE options are. Index points are never options P&L.
- Market data is read-only (GET) via Upstox; no order endpoints are ever called.
- GitHub cron is unreliable; scheduled/manual dispatch is the reliable start.
- CI holds no broker credentials; live reconciliation runs only in the credentialed, manual, read-only workflows.

## Tested rollback design (Phase 1 standard)
Every production-affecting change: preregister a CHG, record its squash-merge SHA in
ops/rollback_manifest.json, and keep the change a single-parent git-only commit so
`scripts/rollback --to <CHG>` can revert it after a rehearsal. Data/deployment restore
(Firestore, journals, APK) is out of source-rollback scope and needs its own plan.

## Change control
This document starts Phase 1. Phases 2–10 remain gated in order; no phase is claimed
complete without its own evidence. Rollback of this doc: git revert.
