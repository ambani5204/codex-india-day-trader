# ALGOBANI risk register (Phase 0)

Paper-only system. "Risk" here = risks to correctness, safety and evidence, not trading P&L advice.

| # | Risk | Likelihood | Impact | Mitigation (status) |
|---|------|-----------|--------|---------------------|
| R1 | A source push starts a credentialed Firestore/paper workflow (incident #58 class) | Low | High | Push triggers removed from cloud-ce-pe-paper (#63) and nightly evaluator (#70); every merge audited for push triggers. |
| R2 | Daily Upstox access token expires → session cannot fetch quotes | High (daily) | High | Manual morning refresh required; session fails closed (no fabricated prices). Open: no automated renewal. |
| R3 | GitHub cron does not fire in the morning window → no session | Medium | High | Manual/scheduled dispatch at 09:05 IST. Open: needs scheduled-task permission. |
| R4 | Full market day exceeds GitHub's 360-min job cap → no SESSION_SUMMARY | High | Medium | Open: split into morning+afternoon jobs (in progress). |
| R5 | Journal token lacks write scope → journals not saved (403) | Resolved | High | Rotated to fine-grained Contents:write token 2026-11-27; write probe passes. |
| R6 | Dashboard shows stale/deleted data | Resolved | Medium | Android now replaces history from Firestore on refresh (journals #9). |
| R7 | Live order placement | N/A | Critical | Hard-prohibited in code and process; paper only, read-only quotes. |
| R8 | Fabricated prices/fills/results | Low | Critical | Fail-closed gates; synthetic data clearly labelled; reconciliation exits non-zero on mismatch. |
| R9 | Destructive data op (delete/backfill) without owner intent | Low | High | Manual-dispatch, dry-run-default, confirm-phrase purge tool; no automated deletes. |
| R10 | No proven strategy edge | Certain | High (for profitability) | Research-only until walk-forward + ≥10 reconciled paper sessions (Phases 8–9). Never claim profitability. |
