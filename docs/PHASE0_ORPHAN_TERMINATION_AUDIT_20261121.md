# CHG-20261121-2059 — P0 orphan lineage and session-termination audit

**Scope:** isolated draft, offline synthetic preflight only. No production writer changes, Firestore reads/writes, deletions, trading orders, or Phase 1 activation.

## Evidence and observations
- Issue #20: credentialed GET-only Firestore CI 44666732450 found `paper_evaluations/2026-11-14` without eligible `PAPER_SIMULATION` history; 2026-11-14 was Saturday. Origin is **unresolved**. Preserve record; do not classify as legacy.
- Current `deploy/nightly_strategy_evaluation.py` on main derives date-scoped reports from `paper_history`, but its `evaluate()` selects only latest snapshot per (date, market). This is **not** a valid session-level reconciliation when retries or strategy-version restarts create legitimate multiple sessions. Its writer uses Firestore PATCH and may overwrite an existing evaluation; this branch deliberately does not change it.
- `.github/workflows/nightly-strategy-evaluation.yml` schedules 23:10 IST weekdays, but also triggers on pushes to evaluator/workflow/test files. Push-triggered publication can happen outside market sessions. A green CI run does not establish a completed trading session or valid provenance.
- Existing report fields `report_date`, `generated_at`, `sessions`, `evaluation_type` do not by themselves prove the originating session IDs, attempt IDs, calendar version, or input document hashes.
- Session termination **not verified**: completion of a GitHub Actions job is not evidence that the paper worker stayed active until 15:30 IST. Need independently inspect start/end, failure/cancellation/retry, lease, source event lineage, and trading calendar, including restarted workflows.

## Required credentialed GET-only follow-up
1. Privately inspect Nov 14 evaluation creation/update metadata, source history archives, report generation workflow run ID, and immutable writer logs. No raw financial values or private IDs in public CI.
2. Verify authoritative NSE/BSE session calendar including special Saturday trading sessions and holidays; weekend alone is not proof no session could exist.
3. Build event identity mapping: market, trading_date, session_id, attempt_id, strategy_version, trade_event_id. Distinguish valid multiple sessions from duplicate snapshots and repeated trade events.
4. Independently reconcile journal↔Firestore and require signed/explicit termination evidence for each session. Treat incomplete/unknown as BLOCKED.
5. Add GET-only dry-run and tested rollback before any proposed writer change; do not overwrite or archive Nov 14 record based on conjecture.

## Change and rollback
- Files: `deploy/phase0_orphan_calendar_preflight.py` and `tests/test_phase0_orphan_calendar_preflight.py` plus this audit.
- Reversible rollback: close draft PR and delete isolated branch. No production change; release rollback remains untested.
- **Phase 0 OPEN / Phase 1 NOT STARTED.**
