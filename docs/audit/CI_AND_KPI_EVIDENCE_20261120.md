# Phase 0 — CI and Firestore aggregation evidence, 2026-11-20 IST

## Fresh CI for audit PR
- GitHub Actions run [44599270198](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44599270198), head `c76f44bfb2b89378a88a28ebbc42147dc6fb236f`: **completed success**.
- Three jobs `test (3.10)`, `test (3.11)`, `test (3.12)`: both `Check syntax` and `Unit tests (offline, no broker keys)` report **success** on each.
- This is a **fresh remote CI execution**, not a local execution, and does not validate runtime trading, Firestore data or Android release. Test totals/coverage were not independently obtained.

## Verified source-level KPI scope mismatch
`deploy/firebase_live_publisher.py` at SHA `f9b473315a7d2923e7f768b90b5c1aa0bd51a7ca`:
- Overall `net_pnl` sums `closed_with_pnl` across all closed events with numeric net P&L.
- `trade_ledger` is intentionally capped to the most recent 30 `PAPER_TRADE_CLOSED` events.
- `strategy_stats` is computed **from that capped trade_ledger** instead of the full closed-event set.
- Consequence: if there are >30 closed trades, overall net P&L and strategy-level net P&L may cover different populations; absent attribution is `UNATTRIBUTED`. This is a **source-confirmed potential defect**, not evidence that a production snapshot actually had >30 trades.
- `publish_history` preserves the previously stored document if any of five coverage counters regress. This can preserve data but does not establish transaction-level merge/idempotency across overlapping runs; inspect before modifying.
- `publish` writes `paper_history/{date_ist}_{market}` first and `paper_dashboard/latest_{market}` second, not an atomic multi-document transaction.

## Required next test-first change (not implemented in Phase 0)
1. Create a synthetic >30 closed-event fixture with two strategies, unique timestamps, and an un-attributed event; assert full-sample strategy totals reconcile with overall `net_pnl` and `closed_trades`.
2. Preserve capped UI `trade_ledger` for Firestore document size; calculate strategy aggregation from full closed events via a shared attribution helper; do not infer from later signals.
3. Assert unknown P&L is `null`, not zero; protect against booleans and incomplete attribution.
4. Verify Firestore writer/reader contract and regression CI; inspect rollback implementation and test rollback before applying to production.
5. Log separate CHG-ID before any code/config change. Keep this audit PR documentation-only.

## Phase gate
Phase 0 **still open**: no database reads, private journal reconciliation, Android API contract matrix, or tested rollback. No production mutations or strategy status changes.
