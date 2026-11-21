# Phase 0 — Firestore source schema / writer-reader-security matrix

**Source verified, deployed DB UNKNOWN.** Date 2026-11-20 IST. Based on primary tree `c1377288910b080ca11cb66e4ed0fcc7d8f2c0cb` and private journals rules blob `9bca028f0037ab3a78f2703bf3f17798befe7c8d`. This is a *code-inferred schema* and **must not be mislabeled as a Firestore schema dump**. Actual field types/null distributions, deployed rule version, indexes, reader UID and collection counts are unknown.

| Collection / doc id | Server writer | Client reader | Source fields, types and coverage | Rules in private repository |
|---|---|---|---|---|
| `paper_history/{YYYY-MM-DD}_{NIFTY/SENSEX}` | `deploy/firebase_live_publisher.py` (same `snapshot()` payload as latest) | Android `loadData` history query; nightly evaluation `main` paginates 100/page | `date_ist:string`, `market:string`, `session_status:string`, `updated_at:ISO string`, `run_id:string`, `signals_count:int`, `entry_event_count:int`, `closed_trades:int`, `net_pnl:float/null`, `gross_pnl:float/null`, `fees_total:float/null`, `winning_trades:int/null`, `losing_trades:int/null`, `max_drawdown:float/null`, `pnl_coverage:int`, `trade_ledger:array<object>`, `strategy_stats:map<string,object>`, `rejected_count:int`, `errors_count:int`, `events:array`, `rejection_events:array`, `data_type=PAPER_SIMULATION`; exact additional fields to confirm by deployed enumeration | owner read only, no client writes |
| `paper_dashboard/latest_{market}` (legacy `latest` reader also present) | `deploy/firebase_live_publisher.py` | Android per-market latest and legacy latest | Same snapshot payload; latest + history written sequentially, not transactionally | owner read only, no client writes |
| `paper_evaluations/{YYYY-MM-DD}`, `latest` | `deploy/nightly_strategy_evaluation.py` | Android Research date-specific fetch | `report_date:string`, `generated_at:string`, `status:string`, `sessions:int`, `closed_trades:int`, `verified_pnl_trades:int`, `net_pnl:float/null`, `win_rate:float/null`, `signals:int`, `risk_rejections:int`, `system_errors:int`, `strategy_reviews:map`, `markets:map`, `change_verified:bool`, `change_status:string`, `before_net_pnl:null`, `after_net_pnl:null`, `evaluation_type:string`. Nightly evaluation reads entire paginated `paper_history` collection and dedupes by date/market before publishing | **No matching allow-read rule in reviewed source**; denied by catch-all if deployed rules match; not a confirmed production permission failure |
| `three_candle_paper/{YYYY-MM-DD}_{market}` | `deploy/publish_three_candle_paper.py` from specialized `deploy/three_candle_live_publisher.py` | Android 3 Candle histories `pageSize=100` | source-specific sidecar fields, journal-derived; exact typed schema contract **not fully verified**. Do not merge financial totals with general paper ledger until ID attribution established | owner read only |
| `ema9_ema15_paper/{YYYY-MM-DD}_{market}` | `deploy/publish_ema9_ema15_paper.py` from specialized `deploy/ema9_ema15_live_publisher.py` | Android EMA 9/15 histories `pageSize=100` | Sidecar summary fields, full deployed type map **not verified**; avoid double-counting | owner read only |
| `three_candle_nightly/{document}` | Research nightly publisher (confirm exact module) | No directly confirmed Android request in inspected `loadData` | **Reader/writer linkage unverified** | owner read only |
| `change_log/{change_id}` | Required by Master Prompt v2 §20.2, **no deployed writer verified** | Future SYSTEM STATUS | Planned typed schema only; no collection existence inferred | No rule in reviewed source |
| `session_state/{session_id}` and durable ledger | Architectural requirement (not deployed) | Future versioned API | Planned. Do not invent deployed collections or records | No rules established |

## Detailed financial nested types and uncertainty

`trade_ledger` from `deploy/firebase_live_publisher.py::snapshot()` is capped to **30** recent closes. Each row derives event data fields: `time`, `entry_time`, `symbol`, `side`, `quantity`, `entry_price`, `exit_price`, `gross_pnl`, `fees`, `net_pnl`, `exit_reason`, `entry_strategy`, `signal_time`, `entry_explanation_available`, `index_spot_at_decision`, `index_stop_at_decision`, `index_target_at_decision`, `risk_budget_inr`, `estimated_stop_loss_inr`, `planned_target_price`, `planned_stop_price`, `planned_reward_risk`, `option_delta`, `selection_basis`. Types follow original JSON event field (often numeric/string/null), not a validated Firestore database distribution.

`strategy_stats` maps strategy ID to objects with `closed_trades:int`, `verified_trades:int`, `winning_trades:int`, `losing_trades:int`, `net_pnl:float/null`, `modeled_stop_total:float`, `modeled_stop_coverage:int`, `stop_exceedances:int`. **Source-confirmed aggregation defect:** its denominator comes from last 30 `trade_ledger` rows, but snapshot `closed_trades` and `net_pnl` cover all closed events. The 31-event synthetic `expectedFailure` regression on audit PR #16 reproduces mismatch. Do not assert that numeric strategy total reconciles when fields/coverage are missing.

`pnl_coverage` counts closed trades with numeric P&L; `net_pnl` may represent a *partial* amount if missing values; consumers should withhold full totals unless `pnl_coverage == closed_trades`, and preserve unknown versus true zero. `data_type=PAPER_SIMULATION` describes paper, not actual broker fills.

## Source security mismatch and release tests

Reviewed `dashboard/firestore.rules` uses `request.auth.uid == "YOUR_FIREBASE_AUTH_UID"` placeholder and owner-only reads for `paper_dashboard`, `paper_history`, `three_candle_paper`, `ema9_ema15_paper`, `three_candle_nightly`; denies all client writes and all other paths. Do **not** paste a real UID or credential into Git. No access rule for `paper_evaluations`. **Deployed rules/owner UID have not been inspected**; run Firebase security-rules emulator tests for authenticated owner, non-owner, unauthenticated and all collection paths against *effective deployed rules* when credentials become available. Avoid an unsafe blanket read grant.

Android `MainActivity.kt` initial `loadData` fetches up to 100 rows of several collections, does not consume `nextPageToken` on those lists, and can silently rely on cached rows on failure. Nightly Python evaluator does paginate. Versioned API and signed session provenance are required before relying on the visual dashboard as an accurate full-history accountant.

## Snapshot/restore and reconciliation blocking evidence

- Repository journal archive inspection: **12** files dated Nov 13–19; **3** `SESSION_SUMMARY`, **9** missing, **4** start-only, **3** numeric closed-paper P&L events totaling **−₹2,786.18**. This does **not** match anything in live Firestore until actual Firestore documents are retrieved and compared by immutable session/trade IDs.
- Private `reports/2026-11-20_ce_pe_audit.md` explicitly says **0 archived journals** for Nov 20 and `No zero-trade conclusion is valid`; do not represent that as healthy/no-signals.
- Firestore history/latest publication is sequential and may partially update; no atomic reconciled snapshot proof.
- Firestore service-account smoke workflow exists but writes/reads/cleans up test records; cannot be substituted for read-only full collection/reconciliation evidence or invoked blindly as an audit-only check.

## Necessary Phase 0 exit probes

1. **Read-only** inventory of actual Firestore document IDs/types/counts, exact rule deployment and timestamps without credential exposure.
2. Reconcile a selected market-date record with private JSONL events; compare closed count, sums/fees and immutable trade IDs, and investigate the nine no-summary sessions. Record mismatches as incidents, never backfill to force totals.
3. Owner vs non-owner permission tests in Firebase rules emulator, including `paper_evaluations`; validate no client writes.
4. Versioned API contract/coverage tests and table of producer/consumer types for *all* sidecars and published nightly collections.
5. Run restore/drill for data/Firestore and a Git + Android release in isolated test environment, record hashes.

**Status:** source schema map complete for core publisher and nightly evaluator; live deployment map and specialized sidecar type maps **INCOMPLETE**. Keep Phase 0 gate open, no production changes. CHG-20261120-0013.
