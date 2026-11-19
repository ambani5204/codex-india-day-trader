# Phase 0 — Architecture, Workflow, Data and Android Audit (Initial Baseline)

Date: **2026-11-20 IST**  
Status: **PARTIAL / NOT EXIT-QUALIFIED** — remotely verified inventory and CI observations; local test execution, Firestore schema inspection, journal reconciliation, and deployment health evidence still required.

## Source snapshots and evidence

| Repository | Access | Observed Git tree at audit | Role |
|---|---|---|---|
| `ambani5204/codex-india-day-trader` | Accessible / push permitted | `c1377288910b080ca11cb66e4ed0fcc7d8f2c0cb` | Python engine, research, workflows, Firestore publishing |
| `ambani5204/codex-trading-journals` | Accessible / push permitted | `1db9169f9b6fc207e353d1699459bd01737fe74f` | Private journal backups, Android project, Firebase dashboard |

**Existing CI baseline (not independently rerun):**
- Trading repo run [44521553711](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44521553711): `compileall` and offline unit-test steps passed on Python 3.10, 3.11, 3.12, 2026-11-19.
- Trading repo run [44538910622](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44538910622): job conclusion **success** but the **Run live option-quote CE/PE paper session** step was **skipped**. Therefore job success != market session success.
- Journals repo run [44489604843](https://github.com/ambani5204/codex-trading-journals/actions/runs/44489604843): Android *debug APK* build completed successfully 2026-11-19; not evidence of signed release, production install, UI tests, or current data correctness.
- Local tests: **NOT RUN**: authenticated Git clone/network access unavailable in the execution container. Do not report test count or pass rates from assumed logs.

## Verified inventory and disposition (provisional)

| Component | Evidence | Disposition | Remaining verification |
|---|---|---|---|
| `india_trader/` Python strategy and paper modules | Repo tree: `advanced_forward.py`, `paper_sim.py`, `options_risk.py`, `research_optimizer.py`, multiple strategy sidecars | **Refactor** toward common interfaces, not immediate deletion | Actual entrypoint calls, deterministic replay parity and options-contract data |
| `deploy/cloud_paper_session.py` | Creates paper-only config and `paper-advanced` workers on an Actions runner; waits to 15:32 IST | **Migrate** session ownership to a durable worker after gate-ready Phase 1–4 | Long-lived lease, checkpoint replay, holiday calendar, uptime |
| `deploy/cloud_session_gate.py` | Deduplicates via querying GitHub Actions runs and checking steps | **Refactor** to durable persisted ownership/TTL; keep existing gate until replacement passes | Failure of GitHub API, restart, conflicting session and lease expiry tests |
| `.github/workflows/cloud-ce-pe-paper.yml` | Multiple weekday cron opportunities, runs 405-minute job, paper-only environment | **Keep** temporarily; later replace long-running execution with watchdog/scheduler | Invariant: no real orders; ensure failure cannot appear as successful session |
| `.github/workflows/test.yml` | Offline tests on Python 3.10/3.11/3.12, syntax checking | **Keep and extend** | Cost examples, schema, replay, Android contract and fault-injection coverage |
| Other `.github/workflows/*` in trading repo | 20 workflow YAML files in repo tree, including historical `*-once` research | **Audit/Archive candidates** (no removals yet) | Trigger matrix, logs, branch references, actual usage; archive only after proof |
| `deploy/firebase_live_publisher.py` and peers | Firestore publisher files and multiple paper sidecars | **Refactor** after Firestore contract audit | Collection/field writer-reader map, aggregation, read-only app security |
| `tests/` | 30+ named test files in repo tree; latest three-Python CI matrix passed | **Keep** | Fresh baseline tests and coverage data |
| Private journal JSONL archives | Multiple dated NIFTY/SENSEX session journals, 2026-11-13 through 2026-11-19 | **Keep; never hard-delete** | Event counts, idempotency, reconciled trades, gaps and restore drill |
| `android-app/.../MainActivity.kt` in journals repo | 82,027-character monolithic native Android Activity with UI and data networking | **Refactor** to Compose/MVVM over phase gates | Existing metric sources, UI golden screenshots, Android tests, stable contract |
| `dashboard/public/index.html` | Compact dark web dashboard with paper positions and trades | **Keep; later refactor** | Actual Firebase data, zero-signal vs stale/error distinctions |
| Android build workflow | Builds `assembleDebug` and uploads artifact | **Keep and extend** | UI tests, signed release, staging/rollback, artifact provenance |

## Findings and risks

**P1 — Incorrect operational confidence from green workflow.** A scheduled workflow can end green when the core paper-session step is skipped (verified run 44538910622). Job conclusion must not be treated as session completion or valid signal coverage. Proposed remediation: explicit session-state event + heartbeat, skip reason, duration, ledger reconciliation and monitoring separated from workflow status.

**P1 — Ephemeral GitHub runner as market-day worker.** Current workflow uses a `timeout-minutes: 405` job, and `deploy/cloud_paper_session.py` launches in-run subprocess workers. Per Master Prompt v2 §5, GitHub Actions may be delayed/cancelled; migrate to durable worker with leases and checkpoints **after** baseline audit and risk gates.

**P1 — Trading integrity unverified.** Actual CE/PE contract, fill and fee model coverage; Firestore exact schema; option-level after-cost P&L; journal counts and live worker uptime are **unknown** until evidenced. Do not claim positive options expectancy.

**P2 — Large Android Activity and unsatisfied release requirements.** App exists and debug APK CI passed, but Compose/MVVM structure, signed release, screenshot tests, explicit API contracts and green/red KPI provenance are not yet verified.

**P2 — Workflow sprawl.** Numerous `once` and overlapping research workflows increase audit/maintenance burden. **Do not disable yet**; first inspect triggers, dependencies, historical runs and rollback.

**Research risk — Mean Reversion V4.** User-provided research report: 0 OOS trades / 0 net R across NIFTY and SENSEX 5m/15m; index-price proxy only. This is **PROXY RESEARCH, NOT OPTIONS P&L**; candidate not qualified. Investigate the 0-trade funnel: candles → signal → filter reason → eligible contract → simulated fill; freeze hypothesis and thresholds before retesting.

## Phase exit evidence checklist

- [x] Both repositories accessible and inventory tree obtained.
- [x] Recent CI **result metadata** examined for Python and Android.
- [x] Green-but-skipped workflow identified and isolated as incident candidate.
- [ ] Execute existing tests against checked-out source with command transcript and version.
- [ ] Produce file-by-file inventory of duplicate workflows, unused strategies and API contracts.
- [ ] Extract exact Firestore schema with writer/reader and security rule verification.
- [ ] Verify 3-year actual option-data coverage (or document precise gaps) and contract notes.
- [ ] Audit session ledger consistency, trade/signal denominators, per-strategy KPI aggregation.
- [ ] Verify scheduler timezone and NSE/BSE trading calendar/holiday behavior.
- [ ] Record quotas, secrets/access review, production health, signed Android/release tests.
- [ ] Produce risk register, audited migration plan and tested `scripts/rollback`.

## Target architecture after Phase 0 exit (design only; not applied)

Shared versioned core IDs/event contracts → validated market data with provenance → pure deterministic strategy engine → option-aware paper execution + costs → independent risk and kill switch → append-only ledger + reconciliation → durable session worker/heartbeat → versioned read-only API + Firestore → Android Compose UI (LIVE, OVERALL, RESEARCH, compact STATUS); isolated research pipeline with walk-forward, trial registry and frozen qualification gates.

Paper trading stays default. Live orders require explicit owner approval. The 60% win-rate goal is an aspiration only; qualification is based on *net* expectancy, confidence bounds, profit factor, drawdown, sample size, stability, slippage stress and forward-paper evidence.

## Change and rollback

This document is part of `CHG-20261120-0001` on isolated branch `audit/phase0-baseline-20261120`. No production code, Android binary, schema, strategy status or workflow configuration has been changed. **Do not merge** until review and the rollback procedure are tested and recorded. Proposed rollback after merge: `scripts/rollback --to CHG-20261120-0001` when implemented; for a one-commit documentation-only merge, `git revert <merge-commit-sha>`. A command with placeholders is not a tested rollback.

## Next action

Complete the baseline, especially Firestore/Journals ledger and scheduled-session traces. Only then enter Phase 1 plan and isolate the first reliability fix in a separately logged, CI-tested, reversible PR.
