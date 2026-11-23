# CHG-20261120-0016 — Pre-record corrected nightly evaluation null-P&L semantics

- 2026-11-20 IST. Audit run [44666541757](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44666541757) completed 7/7 synthetic tests then checked real Firestore. 13/15 read-model comparisons returned MATCH. `paper_evaluations/2026-11-14` returned NO_HISTORY_FOR_DATE; `2026-11-19` returned EVALUATION_INCOMPLETE_COVERAGE.
- Root cause of second warning might be overstrict test: a zero-closed-trade market legitimately has null `net_pnl`, yet comparator rejects *any* null on a day where another market has covered trades. This is a test logic defect, not proven ledger corruption.
- Proposed fix **before** change: require numeric `net_pnl` only in rows whose `pnl_coverage > 0`. Rows with coverage=0 and net_pnl=null add zero to date aggregate but are not claimed profitable. If total coverage < total closed, classify `PARTIAL_FINANCIAL_COVERAGE` and remain blocked. Do not change live Firestore or suppress unaccounted dates.
- Add deterministic two-market synthetic unit test with 1 NIFTY covered trade + 0 SENSEX trades/null P&L and a separate truly partial coverage test.
- Next result must be a new GitHub CI read-only run; do not relabel 2026-11-14 as healthy without investigating its source.
- Rollback: discard unmerged audit branch; nothing deployed.
