# Phase 0 tested-rollback rehearsal — 2026-11-27

Gate: "tested rollback" (Phase 0 exit, #17).

## Method
On a throwaway copy of the repo (`/tmp/rbtest`), CHG-20261127-0955 (the task-queue
merge `aba9453`) was registered in `ops/rollback_manifest.json`, then the real
`scripts/rollback --to CHG-20261127-0955` was executed.

## Result (verified)
- Script exit code 0.
- Created restore branch `restore-points/CHG-20261127-0955-<head>` pointing at pre-rollback HEAD.
- Produced a single `Revert "..."` commit.
- The files added by the change (`deploy/algobani_queue.py`, `deploy/algobani_dispatch.py`) were removed by the revert.
- Full offline suite still passed after the revert (`OK`).
- Script correctly prints `NOT_RESTORED: deployments, Firestore, broker state, private journals, APK` — source rollback only.

## Fail-closed properties confirmed by scripts/rollback + tests/test_source_rollback_gate.py
Refuses: invalid CHG id, dirty worktree, missing/corrupt manifest, unregistered change,
invalid/unavailable SHA, non-ancestor commit, merge/root commit, duplicate restore point.

## Scope limit
This rehearses SOURCE rollback. Deployment/Firestore/journal/APK restore is explicitly
out of scope and requires a separate, independently verified plan (not claimed complete).
