# Phase 1 readiness inputs — Phase 0 handoff only

**Not `docs/PLAN.md`. Not Phase 1 started or completed.** Prepared under CHG-20261120-0017 to make the next agent action deterministic immediately after Phase 0 is exit-qualified.

## Master Prompt v2 Phase 1 contract

The Phase 1 table requires a `PLAN.md` with **milestones, risks, rollback strategy and assumptions**, reviewed against v2. Section 17 prohibits starting Phase 1 before Phase 0 exits. Required Phase 0 evidence: `AUDIT.md`, inventory, current test results, baseline metrics, risk register; test output, failing tests and schema map. Persistent P0 incidents #20 and #21 and actual deployment/rollback gaps prevent claiming the audit exit gate today.

## Candidate milestones once Phase 1 is allowed to begin

| Milestone | Target and acceptance | Dependencies |
|---|---|---|
| P1.1 Evidence contract | One versioned event schema and immutable IDs: session, strategy, trade, contract, config, data provenance; null vs zero semantics and realized-option-only profit | Investigate P0 issues and verify source trading/data calendar |
| P1.2 Reversible delivery | Source/data/config/app restore points; default-deny `scripts/rollback --to CHG-ID`, real observed code/config/schema/app rollback drills; release tags and signed APK retention | PR #19 source-only synthetic test must not be misreported as production drill |
| P1.3 API and security baseline | Read-only versioned `/v1` typed snapshots + Firestore compatibility/migration plan, owner/non-owner rule tests, transaction revision and consistent watermark | Current `paper_evaluations` read mismatch and deployed rules unknown |
| P1.4 Durable operations design | One market-day owner with lease+heartbeat+checkpoint, scheduler holiday/IST normal and delayed start, fault-injection matrix, explicit SKIPPED vs NO_SIGNALS vs COMPLETE_RECONCILED | Existing GitHub ephemeral 405-min market runner and 9 no-summary archives |
| P1.5 Option-data coverage specification | Actual CE/PE contract master, expiry/lot schedule, quote provenance, missing candles, gap budget and accuracy acceptance; index research strictly PROXY | Data quality/coverage unknown |
| P1.6 Strategy/test plan | Preserve zero-qualified Mean Reversion V4, 31+ synthetic KPI regression, numerical fee/tax checks and replay parity, no overfitting | No threshold relaxation or guaranteed 60% win rate |
| P1.7 Android visual-first staged plan | NIFTY-first compact LIVE cards/chart/strategy table, OVERALL, RESEARCH, health sheet, offline/stale handling, screenshot/device/accessibility and read-only security tests | UI draft PR #5 compiled but not installed, app feature flag and rollback untested |
| P1.8 Cost and observability baseline | Actions minutes, actual Firestore reads/writes/quotas, Upstox rate and token refresh, alerts/incidents; avoid expensive repeated probes | Actual billing/resource measurements unavailable |

## Delivery sequence and rollback expectations

Start with P1.1/P1.2 after exit. Prefer a **modular monolith**, shared core event and calendar contracts; preserve all historical journals and old API read model until parity tests. Code one logical change per PR, prerecord change and tested rollback, restore before any schema/data migration, do not hard delete. Stage Android upgrades behind a reversible flag and retain previous signed release. Simulated options P&L must use actual CE/PE contract premiums and after-cost execution, or explicitly mark index-only **PROXY RESEARCH, NOT OPTIONS P&L**. No live orders or increased risk without owner approval.

## Phase 0 clearance checklist — MUST be completed before changing status

- [ ] Close or explicitly reconcile incident [#20](https://github.com/ambani5204/codex-india-day-trader/issues/20) with provenance of Nov14 evaluation and documented valid holiday logic.
- [ ] Restore secure private journal read for the reconciliation runner or use a genuinely nonpublic credential-equipped alternative; compare per-market/day counts, after-cost net and record IDs, resolve nine incomplete journal sessions (incident [#21](https://github.com/ambani5204/codex-india-day-trader/issues/21)).
- [ ] Test actual deployed owner/non-owner Firestore read rules and `paper_evaluations` route without loosening access.
- [ ] Verify exact source/data/config/workflow/signed Android rollback with restore points; no placeholders or toy-only drill.
- [ ] Prove normal/holiday day scheduler, lease/cancellation outcomes and data coverage caveats with immutable logs.
- [ ] Audit/test active workflows, secrets/action SHA pinning, CI resource and API consumption metrics.
- [ ] Record `PHASE0_EXIT_PASS` only after an audit review using test log hashes; otherwise remain in Phase 0 and continue the next unblocked T0 step.

## Autonomy for subsequent runs

Use master issue #17 and PR #22; phase-next task selection uses **verified** records. If private GitHub access remains 404, continue read-only scheduler/holiday, Firestore rule emulation, signed-APK rollback design and workflow quota inventory rather than waiting for owner. Critical asks 0 unless Master §20.1 threshold is reached.
