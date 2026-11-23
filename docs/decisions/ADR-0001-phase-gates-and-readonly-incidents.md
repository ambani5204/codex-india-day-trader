# ADR-0001 — Phase-gated delivery, data integrity stop and parallel UI design

- Date: 2026-11-20 IST
- Status: **PROPOSED during Phase 0 / not a production policy change**
- Source: Master Prompt v2 §§0,3,17,20; owner instruction to prioritize meaningful Android UI.
- Linked change: CHG-20261120-0017; incidents #20, #21.

## Context

The trading repo contains multiple unmerged PRs: #16 audit and synthetic 31-trade aggregation failure; #18 tested nightly JSON report serializer fix; #19 tested **source-only** rollback utility; #22 live read-only phase audit. The private journals repo contains #4 Android visual-first skill and #5 compiled NIFTY-first major LIVE redesign. Production `main` and installed APK remain unchanged. There is a P0 unresolved Firestore orphan evaluation and a P0 journal access gap; real app data reconciliation and release rollback not proven.

Master §17 forbids starting Phase 1 before Phase 0 exits, and stops on unexplained ledger mismatch. The desire for visible UI progress cannot override that order.

## Options considered

1. Merge all green PRs now and modernize UI immediately. **Rejected:** passing unit builds do not prove source-of-truth correctness, app-client permissions, signed release or data rollback.
2. Freeze all engineering and ask owner for routine GitHub/Firebase troubleshooting. **Rejected:** noncritical; violates autonomy.
3. **Chosen:** continue Phase 0 T0 read-only validation, synthetic tests, source inventory, risk/incident tracking and UX acceptance preparation. Keep actual Android/backend feature PRs unmerged and ready for safe, independent testing after phase gates. As access improves, take the next reversible investigation automatically; do not lower risk or research thresholds to pass.

## Implications

- The user sees no falsely claimed installed redesign. CI-built APK is a draft artifact, not a release.
- Do not edit Firestore to “fix” the Nov14 evaluation or invent JSONL close events.
- Do not change credential scopes or deploy broad owner read access without security checks.
- Phase 1 planning deliverable `docs/PLAN.md` is **not** declared complete until the Phase 0 stop conditions are resolved and the prior phase exit is evidenced.
- Preparatory Phase 1 inputs may be documented during Phase 0 to avoid delay but are not a phase transition.
- At Phase 1 start, first milestone is versioned ledger and rollback-first architecture/CI, then compact visual UX based on reconciled backend metrics.

## Rollback / review

No runtime behavior changes in this ADR; abandon draft PR #22 to undo. Merge rollback requires tested method; keep release gate closed. Revisit after private journal-Firestore reconciliation, evaluated orphan provenance, effective client rule tests and rollback proof.
