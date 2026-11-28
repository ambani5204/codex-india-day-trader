# ADR-0003: Durable lease, recovery classification, incident log (Phase 6)

## Status
Accepted 2026-11-28.

## Context
GitHub schedule events can be delayed/dropped and jobs can be retried. The
existing gate (deploy/cloud_session_gate.py) already refuses to retry after a
real worker attempt until "durable resume is verified", but that precondition
was prose, not a mechanism. Phase 6 asks for a durable worker/lease, recovery
and incidents.

## Decision
Three pure, offline, dependency-free modules:
- `india_trader/lease.py` — atomic file lease (temp + os.replace). One holder per
  (market, day); a second live holder is refused; only a stale (heartbeat-expired)
  lease may be taken over, and renew/release require the acquisition token.
- `india_trader/recovery.py` — classifies a journal into CLEAN / NO_SESSION /
  PAUSED_RESUMABLE / UNRESOLVED_NEEDS_RECONCILE / CRASHED_NO_TERMINAL. Only a
  PAUSED handoff may auto-resume; a crash or unresolved position MUST NOT be
  retried automatically. This makes the gate's precondition an inspectable fn.
- `india_trader/incidents.py` — append-only JSONL incident log (stale-lease
  takeover, double-worker blocked, crash, unresolved-on-recovery). Operational
  metadata only; never raw quotes/trades; append-only preserves all records.

## Integration (DEFERRED on purpose)
Wiring these into the live worker/gate is intentionally NOT done in this change.
The two-job split has its first real market validation on Monday 2026-11-30;
changing the live startup path the business day before would risk that proof.
Plan, to land AFTER Monday's run is observed:
1. Worker acquires the lease at startup, heartbeats each loop, releases on the
   terminal event; a refused lease => DOUBLE_WORKER_BLOCKED incident + clean exit.
2. Startup runs recovery.classify on the day's journal; auto-proceed only for
   NO_SESSION or PAUSED_RESUMABLE; otherwise record the incident and exit for
   reconciliation (no silent retry).
3. Gate consults recovery state instead of its heuristic job-step check.

## Consequences
+ Double-execution and silent crash-retry become mechanically preventable.
+ Fully testable offline (tests/test_phase6_durable_worker.py, 11 tests).
- The guarantees are latent until the deferred wiring lands; until then the
  existing fail-closed gate remains the live protection.

## Rollback
git revert the Phase 6 commit. No live path changed, so revert is inert.
