# Phase 0 — Private journal lifecycle and Firestore writer audit, 2026-11-20 IST

Status: **SOURCE/ARCHIVE VERIFIED, LIVE FIRESTORE UNKNOWN**. Audit-only under `CHG-20261120-0003`. Private journal event figures are archived-paper evidence, **not** independently reconciled production database totals or historical option backtest returns.

## Read-only archived journal event inventory

GitHub source: private `ambani5204/codex-trading-journals` repository, tree `1db9169f9b6fc207e353d1699459bd01737fe74f`. All 12 available JSONL files under `journals/2026-11-13` through `journals/2026-11-19` were read via authenticated GitHub connector; 12/12 parsed with no malformed JSON line observed. Event types were counted without modifying a journal.

| Date IST | Market / session prefix | Blob SHA (first 12) | Events | SESSION_SUMMARY | INDEX_SIGNAL | PAPER_TRADE_CLOSED | Closed-trade sum of available numeric net P&L (₹) |
|---|---|---|---:|---:|---:|---:|---:|
| 2026-11-13 | NIFTY / 105722 | `8c3408073b6e` | 219 | 1 | 4 | 1 | -1,140.12 |
| 2026-11-16 | NIFTY / 091756 | `3897226eb2ad` | 51 | 0 | 7 | 1 | -867.82 |
| 2026-11-17 | NIFTY / 093142 | `cb21f2134007` | 21 | 0 | 3 | 0 | n/a |
| 2026-11-17 | NIFTY / 122730 | `e0fd27bc6ac6` | 21 | 0 | 4 | 0 | n/a |
| 2026-11-18 | NIFTY / 092032 | `80c57ca74d81` | 1 | 0 | 0 | 0 | n/a |
| 2026-11-18 | SENSEX / 092032 | `0e70d4e12388` | 1 | 0 | 0 | 0 | n/a |
| 2026-11-18 | NIFTY / 134501 | `b5f53325b1c4` | 11 | 0 | 2 | 0 | n/a |
| 2026-11-18 | SENSEX / 134501 | `dfe657c09a78` | 13 | 0 | 2 | 0 | n/a |
| 2026-11-19 | NIFTY / 113600 | `4d1b3a0f2fa` | 1 | 0 | 0 | 0 | n/a |
| 2026-11-19 | SENSEX / 113600 | `5be9cd320531` | 1 | 0 | 0 | 0 | n/a |
| 2026-11-19 | NIFTY / 115044 | `339a32e34896` | 26 | 1 | 2 | 1 | -778.24 |
| 2026-11-19 | SENSEX / 115044 | `8a1badb012f5` | 14 | 1 | 2 | 0 | n/a |

**Aggregate of inspected files:** 12 sessions; **4** with SESSION_SUMMARY; **8** missing it; **3** PAPER_TRADE_CLOSED with numeric P&L (₹ -2,786.18 in aggregate); **26 INDEX_SIGNAL** event occurrences (NOT unique actionable signals and NOT filled trades). There are **4 start-only journals** (2026-11-18 both markets 092032; 2026-11-19 both markets 113600). There are also other no-summary journals with additional events, including **one closed trade** on 2026-11-16; classify those as **incomplete**, not blank or successfully closed.

**Caveat:** The 2026-11-13 journal has a `SESSION_SUMMARY` timestamp 15:20 IST. Verify intended close-time policy and early termination before counting it as a fully valid market session. Likewise, 2026-11-19 closing summaries must be reconciled against order/position and Firestore state. 4 summaries means 4 *recorded* summaries, not four independently proven successful sessions. A 0 P&L in a journal without closed trades was **not** assumed; report P&L as unavailable.

## Source-verified restart design

`deploy/private_journal_restore.py` blob `972a7b2f2b046158176198101a812dc832ea070a`:
- Confirms destination repository is private and expected; errors out if archive listing is malformed.
- Strictly decodes Base64 JSONL and verifies each line is a JSON object.
- Preserves the archive but **skips rehydrating** a start-only journal when filename, market and session ID match. Subsequent worker starts create new journals.
- Restores non-start-only archives or fails closed if an existing local journal differs byte-for-byte.
- **Unresolved:** no evidence here that every incomplete journal with additional events has a terminal recovery event or that an open position cannot be duplicated after a process crash. Verify replay/idempotency before durable-worker migration.

## Source-verified Firestore writer map

| Writer | Destination | Document ID | Data scope and issue |
|---|---|---|---|
| `deploy/firebase_live_publisher.py` (`f9b473315a7d2923e7f768b90b5c1aa0bd51a7ca`) | `paper_history` | `{date_ist}_{market}` | Market-day snapshots. Preserves some older counters; history/latest writes separate, non-atomic; ledger limited to 30 |
| Same | `paper_dashboard` | `latest_{market}` | Latest per-market paper snapshots. Overall closed P&L full numeric sample, strategy_stats capped to 30 |
| `deploy/nightly_strategy_evaluation.py` (`3bd70e6c0317d7ae614ce7c79b15a8c027a90c98`) | `paper_evaluations` | `{trading_date}` and `latest` | Date-scoped review of Firestore `paper_history`; follows `pageToken` on history reads. Android reader requests date-scoped reports, but inspected rules lack this collection |
| `deploy/publish_three_candle_paper.py` (`97ed36379661caa830aa2850b053918be54dec5b`) | `three_candle_paper` | `{date_ist}_{market}` | Separate sidecar event-derived summaries; inspect event identity and provenance before combining with base strategy counts |
| `deploy/publish_ema9_ema15_paper.py` (`b01555e783c5703ce06d5fb430337ccd0326512b`) | `ema9_ema15_paper` | `{date_ist}_{market}` | EMA sidecar summaries; isolated from base paper ledger |

Read-only Android contract was documented separately in `docs/audit/ANDROID_FIRESTORE_CONTRACT_20261120.md`. Its `paper_evaluations/{date}` request has no allow rule in inspected `dashboard/firestore.rules` (blob `9bca028f0037ab3a78f2703bf3f17798befe7c8d`), **if** those source rules are deployed. Backend uses service credentials; Android uses authenticated Firestore REST reads. Deployed rules, Firestore collection contents, IAM and owner-UID substitution are **UNKNOWN**.

## Phase 0 findings and recommended gates

1. **P1 — interrupted/incomplete archived sessions.** Eight of twelve journal files lack a summary. Require per-session state machines and explicit recovery/incident status, without deleting any archive or converting an interruption to a 0-signal healthy day.
2. **P1 — unreliable session success inference.** Workflow/job CI green does not imply session execution (previously demonstrated via run 44538910622); 4 recorded summaries do not guarantee a reconciled session.
3. **P1 — source contract discrepancy.** `paper_evaluations` data is written, Android requests it, but reviewed rules do not include read permission. Validate effective rules via owner/non-owner emulator tests before scoped rule change.
4. **P1 — financial denominator discrepancy.** 30-record `trade_ledger` must not define whole-day or all-history strategy totals. Regression-test 31+ synthetic closed events with partial data before separate implementation PR.
5. **P2 — collection consistency.** `paper_history` and `paper_dashboard` are sequential writes; evaluate idempotent, revision-stamped atomic publication/reconciliation and stale representation.
6. **P2 — pagination.** Nightly Python evaluation follows historical `pageToken`; Android initial history reads do not. Compare complete history counts before KPI reporting.

**Next eligible work within Phase 0:** Map event fields and strategy IDs across the five writer collections, verify session termination/recovery via GitHub Actions job logs, run Firestore permission and ledger reconciliation tests if credentials/environment permit, and establish a **tested** doc/code/config rollback procedure. Defer application behavior changes and phase advancement until Phase 0 gates are demonstrably satisfied.

## Test, change and rollback evidence

- Observed JSONL parsing was read-only and source-specific. The sum of closed events is an archive aggregate, **not a verified Firestore P&L**. No real orders, migrations, deletions, data replays or backtests performed.
- Pre-change record `ops/changes/2026-11/CHG-20261120-0003.md` precedes this document in isolated draft branch `audit/phase0-baseline-20261120`.
- Post-commit CI and merge status must be obtained separately. Rollback for the *unmerged* branch is abandonment of PR #16; `git revert <doc-merge-sha>` or `scripts/rollback --to CHG-20261120-0003` remains **untested**. Do not merge without tested rollback.
