# Phase 0 Android UI acceptance — evidence gate (audit only)

Change: CHG-20261121-0559. Status: OPEN / NOT VERIFIED. This is an acceptance checklist, **not** a claim that the Android app was built or tested. The previously referenced path `android-app/PHASE0_UI_ACCEPTANCE.md` returned GitHub 404 on this audit branch before creation. The actual Android source/build repository and artifact provenance remain unverified. Trading PR #5 is a closed candle-stop PR, **not** Android UI PR #5. Do not infer Android implementation from its number.

## Required baseline evidence before any release

- [ ] Identify actual Android source repository, package/application ID, active branch and build tooling; verify access to code rather than mockups.
- [ ] Record reproducible baseline build and unit/instrumented test command, commit SHA, CI job link, and result. No CI evidence => NOT TESTED.
- [ ] Verify Firestore/API source of truth for LIVE (current session) versus OVERALL (historical), NIFTY versus SENSEX, market-date in Asia/Kolkata, strategy identity, and paper-only provenance. A historical closed trade must never be silently counted as a live open trade.
- [ ] Verify no-data, null P&L, missing fees, partial coverage, stale quotes, skipped sessions, cancelled workflows, and pending/running/success/failed states render explicitly rather than as zero, green, or fabricated profit.
- [ ] Verify strategy-wise P&L table, after-cost KPI cards, actual-data chart with range and provenance, top-right workflow status detail, accessible text contrast and responsive layout; NIFTY first, SENSEX filter explicit.
- [ ] Capture Android emulator/device screenshots for loading, no-data, live, completed, failed, stale, and partial data; redact sensitive values and confirm accessibility with test evidence.
- [ ] Produce signed/unsigned APK build artifact identity, install/smoke result, release rollback rehearsal with restoration proof, and approved Phase 0 exit before merge/deploy.

## Current independent blockers

- Firestore internal audit run 44666732450: 14/15, 2026-11-14 orphan evaluation (issue #20).
- Private journal reconciliation run 44666175016 failed HTTP404 (issue #21); subsequent token probe 200/200 only establishes access, not full ledger parity.
- Corrected audit branch offline run 44837924788 succeeded; this is **not** an Android test or full live reconciliation.
- Phase 0 exit and tested rollback are missing; Phase 1 cannot start.

## Rollback

This file is audit-only. Revert its single commit on the audit branch if inaccurate; do not alter main, production, Firestore, journals, or APKs. Rollback rehearsal is pending.

## Next action

Locate actual Android source/build path and CI artifacts; fill each acceptance item with evidence links and commit hashes, or explicitly mark blocked. Continue safe read-only ledger provenance investigation in parallel. No real broker orders or fabricated option returns.
