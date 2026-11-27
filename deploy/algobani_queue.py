"""ALGOBANI durable task queue (CHG-20261127-0955, issue #66).

Standalone, credentials-free, non-trading orchestration primitive.

* Durable task IDs stored in a caller-chosen SQLite file (WAL mode).
* Dependency DAG: a dependency must already exist, and ``add_dependency``
  refuses edges that would create a cycle.
* Atomic claim under ``BEGIN IMMEDIATE`` with a lease and a monotonically
  increasing fencing token. Every later mutation by a worker must present
  ``(owner, fence)``; stale holders are refused with ``StaleClaim``.
* Idempotent completion keyed by ``completion_key``: replaying the same
  completion returns ``"duplicate"`` and changes nothing.
* Bounded retries (default 3 attempts), after which the task is ``failed``
  and needs a human.
* Blocked-task diversion: ``block`` parks a task in ``waiting`` (the attempt
  is refunded) so the dispatcher immediately moves on; ``unblock`` returns
  it to ``todo``.
* Completion-triggered dispatch: ``complete`` returns the dependents that
  became ready, and the dispatcher claims again without any schedule wait.
* Watchdog: ``recover_expired`` (run inside every ``claim`` and exposed as
  the ``recover`` CLI command for a scheduler/cron fallback) returns tasks
  whose lease expired to ``todo`` (or ``failed`` when attempts are
  exhausted). Leases use wall-clock time; a large clock step can expire a
  live lease early (the worker is then fenced out and killed, never doubled).
* Refusals of stale holders are persisted as ``stale_refused`` events.

This module never touches Firestore, brokers, journals, GitHub workflows or
orders. It is imported by nothing in the trading path.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
STATUSES = ("todo", "claimed", "waiting", "done", "failed")
DEFAULT_MAX_ATTEMPTS = 3
MIN_LEASE, MAX_LEASE = 1.0, 3600.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    payload TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    fence INTEGER NOT NULL DEFAULT 0,
    owner TEXT,
    lease_expires REAL,
    completion_key TEXT,
    result TEXT,
    blocker TEXT,
    last_error TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deps (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    depends_on TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, depends_on)
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    fence INTEGER,
    owner TEXT,
    detail TEXT
);
"""


class QueueError(Exception):
    """Invalid request (bad ID, unknown dependency, cycle, conflicting add)."""


class StaleClaim(QueueError):
    """The caller does not hold the current lease/fence for the task.

    ``audit`` (task_id, kind, fence, owner, detail) is persisted by ``_tx``
    *after* rollback so refusals survive in the event log.
    """

    def __init__(self, message, audit=None):
        super().__init__(message)
        self.audit = audit


@dataclass(frozen=True)
class Claim:
    task_id: str
    title: str
    payload: dict
    owner: str
    fence: int
    attempt: int
    lease_expires: float


class TaskQueue:
    def __init__(self, path: str, clock: Callable[[], float] = time.time):
        self.path = path
        self.clock = clock
        self._conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ utils
    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except StaleClaim as exc:
            c.execute("ROLLBACK")
            if exc.audit:
                self._event(c, *exc.audit)  # autocommit, outside the rolled-back tx
            raise
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")

    def _event(self, c, task_id, kind, fence=None, owner=None, detail=None):
        c.execute(
            "INSERT INTO events(ts, task_id, kind, fence, owner, detail) VALUES (?,?,?,?,?,?)",
            (self.clock(), task_id, kind, fence, owner, None if detail is None else str(detail)[:2000]),
        )

    @staticmethod
    def _check_id(task_id: str) -> None:
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            raise QueueError(f"invalid task id: {task_id!r}")

    @staticmethod
    def _check_lease(lease_seconds: float) -> float:
        lease = float(lease_seconds)
        if not (MIN_LEASE <= lease <= MAX_LEASE):
            raise QueueError(f"lease must be within [{MIN_LEASE}, {MAX_LEASE}] seconds")
        return lease

    def _row(self, c, task_id):
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise QueueError(f"unknown task: {task_id}")
        return row

    def _require_holder(self, c, task_id, owner, fence):
        row = self._row(c, task_id)
        if row["status"] != "claimed" or row["owner"] != owner or row["fence"] != fence:
            raise StaleClaim(f"{task_id}: caller {owner}@{fence} does not hold current lease",
                             (task_id, "stale_refused", fence, owner,
                              f"status={row['status']} fence={row['fence']}"))
        if row["lease_expires"] is not None and row["lease_expires"] < self.clock():
            raise StaleClaim(f"{task_id}: lease expired",
                             (task_id, "stale_refused", fence, owner, "lease expired"))
        return row

    # ------------------------------------------------------------- authoring
    def add_task(
        self,
        task_id: str,
        title: str,
        payload: Optional[dict] = None,
        depends_on: Iterable[str] = (),
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        priority: int = 100,
    ) -> bool:
        """Create a task. Returns False if an identical task already exists."""
        self._check_id(task_id)
        deps = sorted(set(depends_on))
        for d in deps:
            self._check_id(d)
        if task_id in deps:
            raise QueueError("task cannot depend on itself")
        if not (1 <= int(max_attempts) <= 10):
            raise QueueError("max_attempts must be 1..10")
        body = json.dumps(payload or {}, sort_keys=True)
        now = self.clock()
        with self._tx() as c:
            existing = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if existing is not None:
                old_deps = [r[0] for r in c.execute(
                    "SELECT depends_on FROM deps WHERE task_id=? ORDER BY depends_on", (task_id,))]
                if (existing["title"] == title and existing["payload"] == body and old_deps == deps
                        and existing["max_attempts"] == int(max_attempts)
                        and existing["priority"] == int(priority)):
                    return False
                raise QueueError(f"task {task_id} exists with a different definition")
            for d in deps:
                if c.execute("SELECT 1 FROM tasks WHERE id=?", (d,)).fetchone() is None:
                    raise QueueError(f"unknown dependency: {d}")
            c.execute(
                "INSERT INTO tasks(id,title,payload,priority,status,max_attempts,created,updated)"
                " VALUES (?,?,?,?, 'todo', ?, ?, ?)",
                (task_id, title, body, int(priority), int(max_attempts), now, now),
            )
            c.executemany("INSERT INTO deps(task_id, depends_on) VALUES (?,?)", [(task_id, d) for d in deps])
            self._event(c, task_id, "created", detail=",".join(deps))
        return True

    def add_dependency(self, task_id: str, depends_on: str) -> None:
        with self._tx() as c:
            self._row(c, task_id)
            self._row(c, depends_on)
            if task_id == depends_on or self._reachable(c, depends_on, task_id):
                raise QueueError(f"dependency {task_id} -> {depends_on} would create a cycle")
            c.execute("INSERT OR IGNORE INTO deps(task_id, depends_on) VALUES (?,?)", (task_id, depends_on))
            self._event(c, task_id, "dependency_added", detail=depends_on)

    @staticmethod
    def _reachable(c, start: str, target: str) -> bool:
        """True if ``start`` (transitively) depends on ``target``."""
        seen, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(r[0] for r in c.execute("SELECT depends_on FROM deps WHERE task_id=?", (node,)))
        return False

    # ---------------------------------------------------------------- worker
    def _recover(self, c) -> list:
        now = self.clock()
        rows = c.execute(
            "SELECT id, attempts, max_attempts, owner, fence FROM tasks"
            " WHERE status='claimed' AND lease_expires < ?", (now,)).fetchall()
        out = []
        for r in rows:
            new = "failed" if r["attempts"] >= r["max_attempts"] else "todo"
            c.execute(
                "UPDATE tasks SET status=?, owner=NULL, lease_expires=NULL, last_error=?, updated=? WHERE id=?",
                (new, "lease expired (watchdog)", now, r["id"]))
            self._event(c, r["id"], "lease_expired", r["fence"], r["owner"], new)
            out.append((r["id"], new))
        return out

    def recover_expired(self) -> list:
        """Watchdog: release expired leases. Returns [(task_id, new_status)]."""
        with self._tx() as c:
            return self._recover(c)

    _READY_SQL = (
        "SELECT t.* FROM tasks t WHERE t.status='todo' AND NOT EXISTS ("
        " SELECT 1 FROM deps d JOIN tasks p ON p.id=d.depends_on"
        " WHERE d.task_id=t.id AND p.status!='done')"
    )

    def claim(self, owner: str, lease_seconds: float = 300.0) -> Optional[Claim]:
        """Atomically claim the highest-priority ready task, or return None."""
        if not owner or len(owner) > 200:
            raise QueueError("owner required")
        lease = self._check_lease(lease_seconds)
        with self._tx() as c:
            self._recover(c)
            row = c.execute(self._READY_SQL + " ORDER BY t.priority, t.created, t.id LIMIT 1").fetchone()
            if row is None:
                return None
            now = self.clock()
            fence, attempt, expires = row["fence"] + 1, row["attempts"] + 1, now + lease
            cur = c.execute(
                "UPDATE tasks SET status='claimed', owner=?, fence=?, attempts=?, lease_expires=?, updated=?"
                " WHERE id=? AND status='todo' AND fence=?",
                (owner, fence, attempt, expires, now, row["id"], row["fence"]))
            if cur.rowcount != 1:  # defensive; impossible under BEGIN IMMEDIATE
                raise QueueError("claim race detected")
            self._event(c, row["id"], "claimed", fence, owner, f"attempt={attempt}")
            return Claim(row["id"], row["title"], json.loads(row["payload"]), owner, fence, attempt, expires)

    def heartbeat(self, task_id: str, owner: str, fence: int, lease_seconds: float = 300.0) -> float:
        lease = self._check_lease(lease_seconds)
        with self._tx() as c:
            self._require_holder(c, task_id, owner, fence)
            expires = self.clock() + lease
            c.execute("UPDATE tasks SET lease_expires=?, updated=? WHERE id=?", (expires, self.clock(), task_id))
            self._event(c, task_id, "heartbeat", fence, owner)
            return expires

    def complete(self, task_id: str, owner: str, fence: int, result: Optional[dict] = None,
                 completion_key: Optional[str] = None) -> tuple:
        """Mark done. Returns ("completed"|"duplicate", [newly_ready_ids])."""
        key = completion_key or f"{task_id}@{fence}"
        with self._tx() as c:
            row = self._row(c, task_id)
            if row["status"] == "done":
                if row["completion_key"] == key:
                    self._event(c, task_id, "duplicate_completion", fence, owner)
                    return "duplicate", []
                raise StaleClaim(f"{task_id}: already completed under a different key",
                                 (task_id, "stale_refused", fence, owner, "already done with different key"))
            self._require_holder(c, task_id, owner, fence)
            now = self.clock()
            c.execute(
                "UPDATE tasks SET status='done', owner=NULL, lease_expires=NULL, completion_key=?,"
                " result=?, updated=? WHERE id=?",
                (key, json.dumps(result or {}, sort_keys=True), now, task_id))
            self._event(c, task_id, "completed", fence, owner, key)
            ready = [r["id"] for r in c.execute(
                self._READY_SQL + " AND t.id IN (SELECT task_id FROM deps WHERE depends_on=?) ORDER BY t.id",
                (task_id,))]
            return "completed", ready

    def fail(self, task_id: str, owner: str, fence: int, error: str) -> str:
        """Record a failed attempt. Returns "todo" (will retry) or "failed"."""
        with self._tx() as c:
            row = self._require_holder(c, task_id, owner, fence)
            new = "failed" if row["attempts"] >= row["max_attempts"] else "todo"
            c.execute(
                "UPDATE tasks SET status=?, owner=NULL, lease_expires=NULL, last_error=?, updated=? WHERE id=?",
                (new, str(error)[:2000], self.clock(), task_id))
            self._event(c, task_id, "failed_attempt", fence, owner, f"{new}: {error}")
            return new

    def block(self, task_id: str, owner: str, fence: int, blocker: str) -> None:
        """Divert to ``waiting`` on an external blocker; the attempt is refunded."""
        if not blocker:
            raise QueueError("blocker description required")
        with self._tx() as c:
            self._require_holder(c, task_id, owner, fence)
            c.execute(
                "UPDATE tasks SET status='waiting', owner=NULL, lease_expires=NULL, blocker=?,"
                " attempts=attempts-1, updated=? WHERE id=?",
                (str(blocker)[:2000], self.clock(), task_id))
            self._event(c, task_id, "blocked", fence, owner, blocker)

    def unblock(self, task_id: str, note: str = "") -> None:
        with self._tx() as c:
            row = self._row(c, task_id)
            if row["status"] != "waiting":
                raise QueueError(f"{task_id} is {row['status']}, not waiting")
            c.execute("UPDATE tasks SET status='todo', blocker=NULL, updated=? WHERE id=?", (self.clock(), task_id))
            self._event(c, task_id, "unblocked", detail=note)

    # ------------------------------------------------------------- inspection
    def get(self, task_id: str) -> dict:
        row = self._row(self._conn, task_id)
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        d["depends_on"] = [r[0] for r in self._conn.execute(
            "SELECT depends_on FROM deps WHERE task_id=? ORDER BY depends_on", (task_id,))]
        return d

    def ready_ids(self) -> list:
        return [r["id"] for r in self._conn.execute(self._READY_SQL + " ORDER BY t.priority, t.created, t.id")]

    def counts(self) -> dict:
        out = {s: 0 for s in STATUSES}
        for r in self._conn.execute("SELECT status, COUNT(*) n FROM tasks GROUP BY status"):
            out[r["status"]] = r["n"]
        return out

    def events(self, task_id: Optional[str] = None) -> list:
        q, args = "SELECT * FROM events", ()
        if task_id:
            q, args = q + " WHERE task_id=?", (task_id,)
        return [dict(r) for r in self._conn.execute(q + " ORDER BY seq", args)]

    def stuck_ids(self) -> list:
        """``todo`` tasks that can never become ready because an ancestor failed."""
        rows = self._conn.execute("SELECT id FROM tasks WHERE status='todo' ORDER BY id").fetchall()
        stuck = []
        for r in rows:
            seen, stack = set(), [r["id"]]
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                for d in self._conn.execute(
                        "SELECT p.id, p.status FROM deps d JOIN tasks p ON p.id=d.depends_on WHERE d.task_id=?",
                        (node,)):
                    if d["status"] == "failed":
                        stuck.append(r["id"])
                        stack = []
                        break
                    stack.append(d["id"])
        return stuck

    def requeue(self, task_id: str, note: str = "") -> None:
        """Human action: give a ``failed`` task a fresh attempt budget."""
        with self._tx() as c:
            row = self._row(c, task_id)
            if row["status"] != "failed":
                raise QueueError(f"{task_id} is {row['status']}, not failed")
            c.execute("UPDATE tasks SET status='todo', attempts=0, updated=? WHERE id=?", (self.clock(), task_id))
            self._event(c, task_id, "requeued", detail=note)

    def is_drained(self) -> bool:
        """True when no task is claimed or ready (waiting/failed/stuck may remain)."""
        return self.counts()["claimed"] == 0 and not self.ready_ids()
