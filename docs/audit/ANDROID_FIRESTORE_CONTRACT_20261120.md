# Phase 0 — Android ↔ Firestore Contract Audit (2026-11-20 IST)

Status: **Source-verified / deployment unverified**. Audit-only. Change ID: `CHG-20261120-0002`.

## Exact source versions

- Primary backend: `deploy/firebase_live_publisher.py`, blob `f9b473315a7d2923e7f768b90b5c1aa0bd51a7ca`.
- Android: `android-app/app/src/main/java/in/ambani/papertradingmonitor/MainActivity.kt` in `codex-trading-journals`, blob `4ae9861a2c8ce6e2de5528d98169237da88bb054`.
- Rules: `dashboard/firestore.rules` in `codex-trading-journals`, blob `9bca028f0037ab3a78f2703bf3f17798befe7c8d`.
- No successful real Firestore request, Android runtime test or permission simulation was run in this audit.

## Observed Firestore reader/permission matrix

| Android request in `loadData()` | Reader | Rules in source | Assessment |
|---|---|---|---|
| `paper_dashboard/latest` | Legacy combined latest doc | `paper_dashboard/{document}` owner read | Allowed **only if deployed rules match source and owner UID matches** |
| `paper_dashboard/latest_NIFTY` | Per-market latest | Same | Conditional |
| `paper_dashboard/latest_SENSEX` | Per-market latest | Same | Conditional, configurable display desired |
| `paper_history?pageSize=100` | Session history | `paper_history/{document}` owner read | Conditional; pagination absent |
| `three_candle_paper?pageSize=100` | Sidecar history | `three_candle_paper/{document}` owner read | Conditional; pagination absent |
| `ema9_ema15_paper?pageSize=100` | EMA sidecar history | `ema9_ema15_paper/{document}` owner read | Conditional; pagination absent |
| `paper_evaluations/{researchSelectedDate}` | Nightly strategy evaluation | **No matching allow-read rule**; catch-all deny | **Source-confirmed API/rules contract mismatch** if these rules are deployed; report screen will receive permission denied |
 
Rules also allow owner read on `three_candle_nightly`, deny writes from Android clients for all listed collections, and deny other paths. A placeholder `YOUR_FIREBASE_AUTH_UID` appears in the source rules; deployment-time substitution and actual deployed rules are unknown. **Do not modify rules without verifying publisher schema and owner UID**. Android obtains an auth token; client keys are not authority to write to Firestore.

## Verified KPI denominator mismatch

Publisher `snapshot()` in backend:
- `closed_trades` = full number of `PAPER_TRADE_CLOSED` events.
- `net_pnl` = sum of all numeric non-boolean closed-trade `net_pnl` values.
- `trade_ledger` = **most recent 30** closed trades.
- `strategy_stats` = iterates over **only `trade_ledger`**. Full closed-trade counts and strategy counts may therefore diverge when more than 30 trades occur.
- If the full set contains missing P&L, overall P&L remains partial while strategy P&L may be numeric; preserve explicit coverage metadata rather than converting unknown to zero.

Android `renderCoreStrategy()`, lines 387–425, separately derives strategy trade count, wins/losses and net P&L by iterating **`trade_ledger`** for each history session. It does **not** use the backend's `strategy_stats` object in that function, despite the Master Prompt v2 rule that all financial KPIs be computed server-side from the event ledger. **This compounds the truncated-sample issue.** The computed `netTotal` silently excludes unlisted trades and can show a reassuringly precise amount with no coverage indicator.

## Other contract observations

- The Android reader requests Firestore REST paths directly and constructs per-market + history snapshots, instead of a versioned `/v1` typed API / generated Kotlin client. This is technical debt against the target contract, **not** proof of current service failure.
- `loadData()` uses `pageSize=100` for history/sidecars and does not follow Firestore `nextPageToken` in the inspected function. Results can be incomplete beyond 100 entries.
- On a market-read exception, the code swallows exceptions and keeps cached values; user-facing per-market freshness and error cause require runtime verification.
- App may show NIFTY and SENSEX; desired production display is NIFTY-first with SENSEX optional, not removed from the underlying contract.
- `researchSelectedDate` is a date selector; exact publication period and writer for `paper_evaluations` still need confirmation.

## Next safe steps, no phase skipping

1. Record complete writer schema for `paper_evaluations`, `paper_dashboard`, `paper_history`, and the strategy sidecars, including all document IDs and provenance.
2. Audit effective deployed Firestore rules with authenticated emulator/permission tests using non-owner and owner identities; do not assume source rules are deployed.
3. Build deterministic synthetic fixture of 31+ closed trades across 2 strategies and unknown attribution; verify `sum(strategy_stats[*].net_pnl) == overall net_pnl` **only when all P&L is known**, and `sum(strategy_stats[*].closed_trades) == closed_trades`.
4. In **later gated implementation PR**, make backend statistics full-ledger, keep last-30 trade detail only for display, switch Android KPI consumers to backend totals with coverage timestamps, and add contract/regression tests.
5. Implement the pagination and meaningful stale/error handling under the versioned API refactor.
6. No production deployment or merge until Phase 0 exit evidence, independent test outputs and a **tested rollback** exist.

## Verification and rollback

This is read-only source analysis plus a documentation addition to draft PR #16; **no app, workflow, schema, strategy or capital change**. Current isolation rollback: close draft PR #16; if separately merging documents in future, `git revert <doc-merge-SHA>` after confirming SHA and testing the rollback. The latter has **not** been tested. Do not claim resolved data inconsistencies.
