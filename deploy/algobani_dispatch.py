"""ALGOBANI completion-driven dispatcher (CHG-20261127-0955, issue #66).

Drains ready tasks from a ``TaskQueue`` by running a worker command as a real
subprocess per task. On completion it claims the next ready task immediately
(no schedule wait). The worker contract:

* env ``ALGOBANI_TASK_ID``, ``ALGOBANI_TASK_FENCE``, ``ALGOBANI_TASK_ATTEMPT``
  and ``ALGOBANI_TASK_PAYLOAD`` (JSON) describe the task; the payload is also
  written to the worker's stdin.
* exit 0  -> done (result records exit code, duration and stdout SHA-256 + tail)
* exit 75 -> blocked (EX_TEMPFAIL); last stderr line is the blocker text
* other   -> failed attempt (retried up to the task's max attempts)
* timeout -> failed attempt

The worker command is caller-supplied (e.g. ``codex exec ...`` for an actual
coding agent). This module performs no network, Firestore, broker or GitHub
operations itself and never places orders.

Usage::

    python -m deploy.algobani_dispatch add  --db q.sqlite --id T1 --title "..." [--dep T0] [--payload '{}']
    python -m deploy.algobani_dispatch run  --db q.sqlite --worker-cmd "python worker.py" [--max-tasks N]
    python -m deploy.algobani_dispatch status --db q.sqlite
    python -m deploy.algobani_dispatch unblock --db q.sqlite --id T1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional, Sequence

try:  # package import (tests, python -m deploy.algobani_dispatch)
    from deploy.algobani_queue import Claim, StaleClaim, TaskQueue
except ImportError:  # pragma: no cover - direct script execution
    from algobani_queue import Claim, StaleClaim, TaskQueue  # type: ignore

EX_TEMPFAIL = 75


def subprocess_runner(cmd: Sequence[str], timeout: float = 3600.0,
                      heartbeat: Optional[Callable[[], None]] = None,
                      heartbeat_every: float = 30.0, cwd: Optional[str] = None):
    """Return a runner(claim) -> (outcome, info) that executes ``cmd``."""

    def run(claim: Claim):
        env = dict(os.environ)
        payload = json.dumps(claim.payload, sort_keys=True)
        env.update(ALGOBANI_TASK_ID=claim.task_id, ALGOBANI_TASK_FENCE=str(claim.fence),
                   ALGOBANI_TASK_ATTEMPT=str(claim.attempt), ALGOBANI_TASK_PAYLOAD=payload)
        start = time.monotonic()
        # Output goes to temp files, not pipes, so a verbose worker (e.g. an AI
        # agent) can never deadlock on a full pipe buffer while we poll.
        with tempfile.TemporaryFile("w+") as fout, tempfile.TemporaryFile("w+") as ferr, \
                tempfile.TemporaryFile("w+") as fin:
            fin.write(payload)
            fin.seek(0)
            proc = subprocess.Popen(list(cmd), stdin=fin, stdout=fout, stderr=ferr,
                                    env=env, cwd=cwd, text=True)
            deadline = start + timeout
            next_hb = start + heartbeat_every
            while proc.poll() is None:
                now = time.monotonic()
                if now >= deadline:
                    proc.kill()
                    proc.wait()
                    return "failed", {"error": f"timeout after {timeout}s", "pid": proc.pid}
                if heartbeat and now >= next_hb:
                    try:
                        heartbeat()
                    except Exception as exc:  # lease lost: stop the worker, never orphan it
                        proc.kill()
                        proc.wait()
                        return "failed", {"error": f"lease lost: {exc}", "pid": proc.pid}
                    next_hb = now + heartbeat_every
                time.sleep(min(0.05, max(0.0, deadline - now)))
            fout.seek(0)
            ferr.seek(0)
            out, err = fout.read(), ferr.read()
        info = {
            "exit_code": proc.returncode,
            "pid": proc.pid,
            "duration_s": round(time.monotonic() - start, 3),
            "stdout_sha256": hashlib.sha256(out.encode()).hexdigest(),
            "stdout_tail": out[-500:],
        }
        if proc.returncode == 0:
            return "done", info
        last_err = (err.strip().splitlines() or [f"exit {proc.returncode}"])[-1][:500]
        if proc.returncode == EX_TEMPFAIL:
            info["blocker"] = last_err
            return "blocked", info
        info["error"] = last_err
        return "failed", info

    return run


def drain(queue: TaskQueue, runner, owner: str, lease_seconds: float = 300.0,
          max_tasks: Optional[int] = None, log: Callable[[str], None] = lambda m: None) -> list:
    """Claim -> run -> settle, repeatedly, until no ready task remains.

    Returns a list of (task_id, fence, outcome) in execution order.
    """
    history = []
    while max_tasks is None or len(history) < max_tasks:
        claim = queue.claim(owner, lease_seconds)
        if claim is None:
            break
        log(f"CLAIMED {claim.task_id} fence={claim.fence} attempt={claim.attempt}")
        try:
            outcome, info = runner(claim)
        except Exception as exc:  # worker harness crash -> failed attempt
            outcome, info = "failed", {"error": f"runner exception: {exc!r}"}
        try:
            if outcome == "done":
                status, ready = queue.complete(claim.task_id, owner, claim.fence, info)
                log(f"DONE {claim.task_id} ({status}); newly ready: {ready or 'none'}")
            elif outcome == "blocked":
                queue.block(claim.task_id, owner, claim.fence, info.get("blocker", "blocked"))
                log(f"BLOCKED {claim.task_id}: {info.get('blocker')} -> waiting; moving on")
            else:
                new = queue.fail(claim.task_id, owner, claim.fence, info.get("error", "failed"))
                log(f"FAILED {claim.task_id} -> {new}")
                outcome = f"failed->{new}"
        except StaleClaim as exc:
            log(f"STALE {claim.task_id}: {exc}")
            outcome = "stale"
        history.append((claim.task_id, claim.fence, outcome))
    return history


def _owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="algobani_dispatch")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--db", required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--dep", action="append", default=[])
    a.add_argument("--payload", default="{}")
    a.add_argument("--max-attempts", type=int, default=3)
    a.add_argument("--priority", type=int, default=100)
    r = sub.add_parser("run")
    r.add_argument("--db", required=True)
    r.add_argument("--worker-cmd", required=True)
    r.add_argument("--lease", type=float, default=300.0)
    r.add_argument("--timeout", type=float, default=3600.0)
    r.add_argument("--max-tasks", type=int)
    r.add_argument("--owner", default=None)
    s = sub.add_parser("status")
    s.add_argument("--db", required=True)
    u = sub.add_parser("unblock")
    u.add_argument("--db", required=True)
    u.add_argument("--id", required=True)
    u.add_argument("--note", default="")
    args = p.parse_args(argv)

    q = TaskQueue(args.db)
    try:
        if args.cmd == "add":
            created = q.add_task(args.id, args.title, json.loads(args.payload), args.dep,
                                 args.max_attempts, args.priority)
            print(json.dumps({"id": args.id, "created": created}))
        elif args.cmd == "run":
            owner = args.owner or _owner()
            lease = args.lease
            state = {}

            def hb():
                c = state.get("claim")
                if c:
                    q.heartbeat(c.task_id, owner, c.fence, lease)

            inner = subprocess_runner(shlex.split(args.worker_cmd), args.timeout, hb,
                                      heartbeat_every=max(1.0, lease / 3))

            def runner(claim):
                state["claim"] = claim
                try:
                    return inner(claim)
                finally:
                    state.pop("claim", None)

            hist = drain(q, runner, owner, lease, args.max_tasks, log=lambda m: print(m, flush=True))
            print(json.dumps({"executed": hist, "counts": q.counts()}))
        elif args.cmd == "status":
            print(json.dumps({"counts": q.counts(), "ready": q.ready_ids()}))
        elif args.cmd == "unblock":
            q.unblock(args.id, args.note)
            print(json.dumps({"id": args.id, "status": "todo"}))
    finally:
        q.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
