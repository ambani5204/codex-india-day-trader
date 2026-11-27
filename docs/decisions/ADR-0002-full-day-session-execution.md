# ADR-0002 — Full-day paper session execution under the 360-minute runner cap

- Date: 2026-11-27 IST
- Status: PROPOSED (Phase 1, milestone M1). No code change in this ADR.
- Linked: docs/PLAN.md M1; risk R4; issue #17.

## Problem (verified)
A market day runs 09:15–15:30 IST. The paper worker (`india_trader/advanced_forward.py`)
starts at 09:15, loops until 15:30, and **explicitly never backfills missed candles**
(its own log line). The orchestrator (`deploy/cloud_paper_session.py`) waits until a
15:32 deadline. The whole session is one GitHub-hosted job (`cloud-ce-pe-paper.yml`,
`timeout-minutes: 405`).

GitHub-hosted jobs are hard-capped at **360 minutes**. 09:15→15:32 is ~377 minutes, so
an on-time start is SIGKILLed around 15:15, before the worker writes `SESSION_SUMMARY`.
That is the confirmed cause of the 2026-11-16 missing summary and the reconciliation
`MISSING_SESSION_SUMMARY` outcomes.

Two naive "fixes" are rejected:
- **Start later (e.g. 09:45) to fit the cap** — rejected: the worker never backfills, so
  ORB and early EMA signals in the opening range would be lost.
- **Close positions at a mid-day cutoff and restart** — rejected: a forced exit is a
  fabricated fill; AGENTS.md requires open positions stay unresolved, never backfilled.
  The restart gate (`previous_day_state`) also refuses to resume while a prior same-day
  session has an open position or no summary.

## Options

### Option A — Self-hosted / own-device runner (recommended)
Run `cloud-ce-pe-paper.yml` on a self-hosted runner (the repo already ships
`deploy/termux_runner.py` + `install.sh`). Self-hosted jobs have no 360-minute cap, so
the existing single-job session runs unchanged 09:15→15:32 and writes `SESSION_SUMMARY`
normally. Lowest code risk; needs an always-on device (a spare Android/PC) the owner controls.

### Option B — Validated two-job handoff (morning → afternoon)
Split into `paper_morning` (09:15→~12:30) and `paper_afternoon: needs: paper_morning`
(resume→15:32). Requires real worker changes:
1. A `--stop-at HHMM` that pauses WITHOUT closing open positions, persisting the open
   position and day-limit state to a durable artifact + private journal (no fake exit).
2. A resume mode where `previous_day_state` accepts an intentionally-paused session
   (new `SESSION_PAUSED` marker) and rehydrates the open position, distinct from the
   current "unfinished session" refusal.
3. Artifact/journal state transfer between the two jobs.
Higher risk (open-position integrity); MUST have one supervised full-day validation before merge.

### Option C — Fail-closed cap preflight (interim, low value)
Keep one job but refuse to start a session that cannot finish within the runner's remaining
budget, reporting INCOMPLETE explicitly instead of a silent SIGKILL. Does not enable a full
day; only makes the failure honest. Useful only until A or B lands.

## Decision
Recommend **Option A** as the durable fix (no fabricated fills, minimal code risk). Keep
**Option B** specified for cloud-only operation, to be implemented behind tests and a
supervised full-day validation. Implement **Option C** as an interim safety net.

## Owner input needed
Is an always-on self-hosted runner device available (Option A)? If not, authorise the
Option B worker changes knowing they need one supervised full-day validation run.
