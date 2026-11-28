# ALGOBANI data & security contracts (Phase 2)

Machine-readable contracts enforced in CI (test.yml, Python 3.10/3.11/3.12).

## Event-ledger contract — `india_trader/event_ledger.py` (SCHEMA_VERSION 1.0)
The per-session journals are the event ledger: append-only JSONL, one event per line.

- **Universal fields** (every event): `event`, `timestamp` (ISO-8601, timezone-aware).
- **Per-event required fields** — `EVENT_REQUIRED`, e.g. SESSION_START needs
  `session, market, capital, mode`; SESSION_SUMMARY needs `session, market, status, summary`;
  INDEX_SIGNAL needs `market, side, strategy`; etc. Optional/diagnostic fields are allowed.
- **Ordering invariants** (`validate_ledger`): non-empty; first event is SESSION_START;
  timestamps non-decreasing; the ledger ends in a TERMINAL event
  (SESSION_SUMMARY, UNRESOLVED_POSITION, or SESSION_PAUSED) — fail closed otherwise.
- Validated in CI (`tests/test_event_ledger.py`) and against real production journals
  (2026-11-27 NIFTY + SENSEX both VALID).

## Security contract — `tests/test_security_contract.py`
- **Read-only market data:** `india_trader/upstox.py` uses `method='GET'` only; no POST/PUT/DELETE,
  no order endpoints.
- **No order placement anywhere:** no source contains `place_order(` / `/v2/order` / `/v3/order` etc.
- **Fail-closed order gates:** the live session (`deploy/cloud_paper_session.py`) forces
  `allow_live_orders=False`; worker gates refuse to run unless `paper=true` and orders disabled.
- **No hardcoded secrets:** no `access_token/api_key/secret/password = "<long literal>"` in source.

## CI
`test.yml` runs the full offline suite (including the two contracts above) on every push and PR,
across Python 3.10/3.11/3.12. A contract violation fails CI and blocks merge.

## Schema (Firestore)
The Firestore document schema and its source map are recorded in
`docs/audit/FIRESTORE_SCHEMA_SOURCE_MAP_20261120.md`; internal consistency is checked by the
read-only reconcile workflow (phase0-firestore-internal-reconcile), which reported MATCH on 2026-11-27.

## Versioning
`SCHEMA_VERSION` bumps when the event contract changes, so an old ledger is never silently
accepted under a new contract.
