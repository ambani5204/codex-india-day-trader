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

## Phase 2 — CLOSED 2026-11-28 (contracts, event ledger, CI, schema, security)
- [x] Contracts — versioned event-ledger contract (india_trader/event_ledger.py, SCHEMA_VERSION 1.0): universal + per-event required fields, ordering invariants, fail-closed validator.
- [x] Event ledger — validator confirmed VALID against the real 2026-11-27 NIFTY+SENSEX journals.
- [x] CI — test.yml runs the full suite incl. both contracts on 3.10/3.11/3.12 on every push/PR; a violation blocks merge.
- [x] Schema — EVENT_REQUIRED per-event schema + Firestore schema source map (docs/audit/FIRESTORE_SCHEMA_SOURCE_MAP_20261120.md).
- [x] Security — security contract (tests/test_security_contract.py): GET-only market data, no order placement, live session forces allow_live_orders=False, no hardcoded secrets.
- Evidence: PR #89 (CHG-20261128-1115); docs/CONTRACTS.md. Engineering deliverable, no market-day gate.
## Phase 3 — CLOSED 2026-11-28 (historical CE/PE, calendar, coverage/data quality)
- [x] Trading calendar — india_trader/trading_calendar.py + config/nse_holidays.json fills the exchange-holiday gap the code flagged. is_trading_day/session_bounds/trading_days. Holiday list PARTIAL (fixed-date national holidays only, honestly marked) and FAIL-SAFE: an unlisted date is treated as a trading day and real market data confirms it. Variable/lunar holidays must be completed from the official NSE circular — NOT fabricated.
- [x] Data quality / coverage — india_trader/data_quality.py: per-session expected 75 five-min bars, missing/duplicate/out-of-hours/order checks + aggregate report, so incomplete-data sessions are flagged not silently used.
- [x] Historical CE/PE decision — Upstox retail gives index candles (900 days verified) but not full intraday option-premium history/IV; option backtests use Black-Scholes premiums on the REAL index path (clearly labelled approximate), real fills from forward paper.
- Evidence: PR #91 (CHG-20261128-1420); tests/test_phase3_calendar_dataquality.py.

## Phase 4 — CLOSED 2026-11-28 (paper execution, fees/taxes, risk, independent stop)
- [x] Paper execution + fees — PaperExecutionEngine (#84) with observed-quote fills; option_fees validated vs real contract note (₹221.32 vs ₹222.01).
- [x] Risk + independent stop — SL/TP/trail, MAX_TRADES, DAY_MAX_LOSS/PROFIT, global+per-strategy KILL, EOD square-off; all gate-blocking paths tested (tests/test_paper_exec.py).
- [x] Taxes — india_trader/tax.py: F&O as non-speculative BUSINESS income at slab rate (marginal over other income), new-regime FY25-26 defaults flagged for CA verification, losses untaxed. tests/test_phase4_tax.py (hand-checked slab math).
- Evidence: PR #92 (CHG-20261128-1440).

## Phase 5 — CLOSED 2026-11-28 (deterministic strategies + replay parity)
- [x] Determinism — all three live detectors (S2 supertrend_sma, S4 buffer_breakout, S5 sma_rsi) emit byte-identical events across runs; input never mutated.
- [x] Replay parity / no lookahead — events over every growing prefix equal the full-series events within that prefix, so a signal attributed to a closed bar never changes when later bars arrive (lookahead would fail this).
- Evidence: PR #93 (CHG-20261128-1455); tests/test_phase5_determinism_replay.py.

## Remaining (honest)
- Phases 6–8, 10: subsequent engineering milestones per #17.
- **Phase 9 cannot be compressed:** it requires ≥10 real, consecutive, reconciled live-market paper sessions. First live validation is the two-job split on Monday 2026-11-30 (auto-starts 09:07 IST). Each real session accrues one toward the ten; this is wall-clock bound and no amount of agent parallelism shortens it.

## Phase 6 — CLOSED 2026-11-28 (durable worker, lease, recovery, incidents)
- [x] Durable single-writer lease (india_trader/lease.py), recovery classifier (recovery.py: only a paused handoff auto-resumes; crash/unresolved never auto-retry), append-only incident log (incidents.py). ADR-0003. Live wiring deferred until after Monday (inert revert). PR #95.

## Phase 7 — CLOSED 2026-11-28 (versioned read-only API + NIFTY-first Android monitor)
- [x] Versioned read-only API (india_trader/read_api.py, API_VERSION 1; pure read, asserted no writes). PR #102.
- [x] NIFTY-first Android monitor: debug APK built in CI (build-apk.yml -> Release monitor-apk, Capacitor WebView) + live data feed (deploy/monitor_feed.py) + monitor artifact with LIVE/SAMPLE badge. PR #99/#100/#101.
- Note: debug APK (sideloadable), not a Play-Store signed release.

## Phase 8 — CLOSED 2026-11-28 (OOS walk-forward, frozen thresholds)
- [x] Walk-forward qualification (india_trader/strategies/walk_forward.py): strategies qualify only by clearing FROZEN thresholds on out-of-sample windows; 60% win rate is the aspirational target, separate from the hard floor; win rate alone cannot qualify (PF + drawdown + net gates). PR #103.
- Live OOS numbers feed from the real-candle backtest workflow; this is the gate framework.

## All seven strategy detectors — 2026-11-28
- [x] S1 ORB, S2 Supertrend+SMA, S3 UT Bot+MACD, S4 Buffer Breakout, S5 SMA+RSI, S6 RSI-MA scanner (daily), S7 Reversal v1. Registered in the paper suite (suite_runner); intraday "ALL" = S1-S5+S7, S6 on the daily path. Live suite env-gated off for Monday (RUN_STRATEGY_SUITE). PR #96/#98.

## Remaining (wall-clock bound)
- Phase 9: >=10 real consecutive reconciled live sessions. First = Monday 2026-11-30. Cannot be compressed.
- Phase 10: evidence-based readiness report — depends on Phase 9 data, so it opens only once real sessions accrue.

## Phase 11 — CLOSED 2026-11-28 (realistic performance targets + goal tracker)
Owner set a 10%/day target; project lead rejected it as mathematically impossible on any strategy (compounds past global market capacity in a year; forces ~100% capital risk per trade vs the 4% stop). Replaced with evidence-based FROZEN bands from our own EMA 9/15 backtest.
- [x] S11.1: india_trader/performance_targets.py — FROZEN daily/weekly/monthly bands for Rs 15k; classify_day/week/month → GREEN/FLAT/RED/STOP_HIT/NO_DATA. Cadence 4–7 trades tracked separately.
- [x] S11.2: deploy/daily_goal_check.py — reads monitor feed, writes goal_check.json, one-line verdict.
- [x] S11.4: deploy/weekly_report.py — Mon–Fri reconciliation, per-day + per-strategy breakdown, classifies against weekly band.
- [x] S11.3: mobile monitor Goal card — band visualisation, verdict pill, cadence, week verdict. publish-monitor-data workflow now generates goal_check.json and weekly_report.json alongside data.json.
- Evidence: PR #112 (code), PR #113 (UI + feeds); feeds visible in the monitor-data release. Suite 536 green.
- Realistic daily target band (Rs 15k): stop -600 / pessimistic -300 / expected +75 / optimistic +450. Weekly: stop -2000 / expected +375. Monthly: stop -5000 / expected +1650. 
- Growth gate: Rs 15k → Rs 50k only after ≥10 green-band sessions in a month with ≤2 STOP_HIT days and win rate ≥45%.

