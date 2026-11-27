"""Synthetic, credential-free tests for the ALGOBANI task queue (#66, CHG-20261127-0955)."""

import json
import multiprocessing as mp
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from deploy import algobani_dispatch as dispatch
from deploy.algobani_queue import QueueError, StaleClaim, TaskQueue


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split()[2] != "Z"
    except FileNotFoundError:
        return False
    except OSError:  # pragma: no cover
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _claimer(db, owner, out_q):
    q = TaskQueue(db)
    got = []
    while True:
        c = q.claim(owner, 60)
        if c is None:
            break
        got.append((c.task_id, c.fence))
        q.complete(c.task_id, owner, c.fence, {"by": owner})
    q.close()
    out_q.put(got)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "q.sqlite")
        self.clock = Clock()
        self.q = TaskQueue(self.db, clock=self.clock)

    def tearDown(self):
        self.q.close()
        self.tmp.cleanup()


class DagTests(Base):
    def test_dependency_order_and_completion_triggered_ready(self):
        self.q.add_task("A", "a")
        self.q.add_task("B", "b", depends_on=["A"])
        self.q.add_task("C", "c", depends_on=["A"])
        self.q.add_task("D", "d", depends_on=["B", "C"])
        self.assertEqual(self.q.ready_ids(), ["A"])
        c = self.q.claim("w1", 60)
        status, ready = self.q.complete("A", "w1", c.fence)
        self.assertEqual((status, ready), ("completed", ["B", "C"]))
        for _ in range(2):
            c = self.q.claim("w1", 60)
            _, ready = self.q.complete(c.task_id, "w1", c.fence)
        self.assertEqual(ready, ["D"])

    def test_unknown_dependency_self_and_cycle_refused(self):
        self.q.add_task("A", "a")
        self.q.add_task("B", "b", depends_on=["A"])
        with self.assertRaises(QueueError):
            self.q.add_task("X", "x", depends_on=["missing"])
        with self.assertRaises(QueueError):
            self.q.add_task("Y", "y", depends_on=["Y"])
        with self.assertRaises(QueueError):
            self.q.add_dependency("A", "B")

    def test_add_is_idempotent_but_conflicts_refused(self):
        self.assertTrue(self.q.add_task("A", "a", {"k": 1}))
        self.assertFalse(self.q.add_task("A", "a", {"k": 1}))
        with self.assertRaises(QueueError):
            self.q.add_task("A", "a", {"k": 2})
        with self.assertRaises(QueueError):
            self.q.add_task("A", "a", {"k": 1}, priority=5)

    def test_invalid_ids_and_leases(self):
        for bad in ("", "-x", "a b", "x" * 200, None):
            with self.assertRaises(QueueError):
                self.q.add_task(bad, "t")
        self.q.add_task("A", "a")
        with self.assertRaises(QueueError):
            self.q.claim("w", 0.1)
        with self.assertRaises(QueueError):
            self.q.claim("", 60)


class LeaseFencingTests(Base):
    def setUp(self):
        super().setUp()
        self.q.add_task("A", "a")

    def test_single_claim_and_fencing(self):
        c = self.q.claim("w1", 60)
        self.assertEqual((c.task_id, c.fence, c.attempt), ("A", 1, 1))
        self.assertIsNone(self.q.claim("w2", 60))
        with self.assertRaises(StaleClaim):
            self.q.complete("A", "w2", 1)
        with self.assertRaises(StaleClaim):
            self.q.complete("A", "w1", 99)

    def test_duplicate_completion_is_idempotent(self):
        c = self.q.claim("w1", 60)
        self.assertEqual(self.q.complete("A", "w1", c.fence, {"r": 1})[0], "completed")
        self.assertEqual(self.q.complete("A", "w1", c.fence, {"r": 2})[0], "duplicate")
        self.assertEqual(self.q.get("A")["result"], {"r": 1})
        with self.assertRaises(StaleClaim):
            self.q.complete("A", "w1", c.fence, completion_key="other")
        kinds = [e["kind"] for e in self.q.events("A")]
        self.assertEqual(kinds.count("completed"), 1)
        self.assertEqual(kinds.count("stale_refused"), 1)  # refusal persisted despite rollback
        self.assertIn("duplicate_completion", kinds)

    def test_crash_recovery_and_immediate_reassignment_fences_old_owner(self):
        old = self.q.claim("crashed", 30)
        self.clock.t += 10
        self.q.heartbeat("A", "crashed", old.fence, 30)  # alive for now
        self.clock.t += 31  # worker dies, lease lapses
        new = self.q.claim("w2", 30)  # watchdog runs inside claim
        self.assertEqual((new.task_id, new.fence, new.attempt), ("A", 2, 2))
        with self.assertRaises(StaleClaim):
            self.q.heartbeat("A", "crashed", old.fence, 30)
        with self.assertRaises(StaleClaim):
            self.q.complete("A", "crashed", old.fence)
        self.assertEqual(self.q.complete("A", "w2", new.fence)[0], "completed")
        self.assertIn("lease_expired", [e["kind"] for e in self.q.events("A")])

    def test_expired_holder_cannot_complete_before_watchdog(self):
        c = self.q.claim("w1", 5)
        self.clock.t += 6
        with self.assertRaises(StaleClaim):
            self.q.complete("A", "w1", c.fence)
        self.assertEqual(self.q.recover_expired(), [("A", "todo")])


class RetryBlockTests(Base):
    def test_bounded_retries_then_failed(self):
        self.q.add_task("A", "a")
        self.q.add_task("B", "b", depends_on=["A"])
        outcomes = []
        for _ in range(3):
            c = self.q.claim("w", 60)
            outcomes.append(self.q.fail("A", "w", c.fence, "boom"))
        self.assertEqual(outcomes, ["todo", "todo", "failed"])
        self.assertIsNone(self.q.claim("w", 60))  # dependent B stays locked
        self.assertEqual(self.q.counts()["failed"], 1)
        self.assertEqual(self.q.stuck_ids(), ["B"])
        self.assertTrue(self.q.is_drained())
        self.q.requeue("A", "human fixed env")
        c = self.q.claim("w", 60)
        self.assertEqual((c.task_id, c.attempt), ("A", 1))

    def test_watchdog_exhaustion_marks_failed(self):
        self.q.add_task("A", "a", max_attempts=1)
        self.q.claim("w", 5)
        self.clock.t += 6
        self.assertEqual(self.q.recover_expired(), [("A", "failed")])

    def test_blocked_task_diverts_and_pipeline_continues(self):
        self.q.add_task("A", "a", priority=1)
        self.q.add_task("B", "b", priority=2)
        c = self.q.claim("w", 60)
        self.q.block("A", "w", c.fence, "waiting on CI")
        self.assertEqual(self.q.get("A")["status"], "waiting")
        self.assertEqual(self.q.get("A")["attempts"], 0)  # refunded
        nxt = self.q.claim("w", 60)
        self.assertEqual(nxt.task_id, "B")
        self.q.complete("B", "w", nxt.fence)
        self.assertTrue(self.q.is_drained())
        self.q.unblock("A", "CI green")
        again = self.q.claim("w", 60)
        self.assertEqual((again.task_id, again.fence, again.attempt), ("A", 2, 1))


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_processes_claim_each_task_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "q.sqlite")
            q = TaskQueue(db)
            for i in range(40):
                q.add_task(f"T{i:02d}", f"t{i}")
            q.close()
            ctx = mp.get_context("spawn")
            out = ctx.Queue()
            procs = [ctx.Process(target=_claimer, args=(db, f"w{i}", out)) for i in range(6)]
            for p in procs:
                p.start()
            results = [out.get(timeout=120) for _ in procs]
            for p in procs:
                p.join(timeout=60)
            claimed = [tid for r in results for tid, _ in r]
            self.assertEqual(sorted(claimed), [f"T{i:02d}" for i in range(40)])
            self.assertEqual(len(claimed), len(set(claimed)))
            q = TaskQueue(db)
            self.assertEqual(q.counts()["done"], 40)
            q.close()


class DispatcherTests(Base):
    def _worker(self, body):
        path = Path(self.tmp.name) / "worker.py"
        path.write_text(textwrap.dedent(body))
        return [sys.executable, str(path)]

    def test_two_successive_tasks_run_by_subprocess_worker_without_schedule_wait(self):
        marker = Path(self.tmp.name) / "ran.log"
        cmd = self._worker(f"""
            import json, os, sys
            payload = json.loads(sys.stdin.read())
            with open({str(marker)!r}, "a") as fh:
                fh.write(os.environ["ALGOBANI_TASK_ID"] + ":" + payload["msg"] + ":" + str(os.getpid()) + "\\n")
            print("ok", os.environ["ALGOBANI_TASK_ID"])
        """)
        self.q.add_task("T1", "first", {"msg": "one"})
        self.q.add_task("T2", "second", {"msg": "two"}, depends_on=["T1"])
        hist = dispatch.drain(self.q, dispatch.subprocess_runner(cmd, timeout=60), "disp", 60)
        self.assertEqual(hist, [("T1", 1, "done"), ("T2", 1, "done")])
        lines = marker.read_text().splitlines()
        self.assertEqual([l.split(":")[:2] for l in lines], [["T1", "one"], ["T2", "two"]])
        self.assertNotEqual(lines[0].split(":")[2], str(os.getpid()))  # real separate process
        self.assertEqual(self.q.get("T2")["result"]["exit_code"], 0)

    def test_worker_exit_codes_map_to_block_retry_and_fail(self):
        cmd = self._worker("""
            import os, sys
            tid = os.environ["ALGOBANI_TASK_ID"]
            if tid == "BLK":
                sys.stderr.write("need human reply\\n"); sys.exit(75)
            if tid == "BAD":
                sys.stderr.write("tests failed\\n"); sys.exit(1)
        """)
        self.q.add_task("BLK", "b", priority=1)
        self.q.add_task("BAD", "x", priority=2)
        self.q.add_task("OK", "ok", priority=3)
        hist = dispatch.drain(self.q, dispatch.subprocess_runner(cmd, timeout=60), "disp", 60)
        self.assertEqual([h[2] for h in hist],
                         ["blocked", "failed->todo", "failed->todo", "failed->failed", "done"])
        self.assertEqual(self.q.get("BLK")["blocker"], "need human reply")
        self.assertEqual(self.q.counts(), {"todo": 0, "claimed": 0, "waiting": 1, "done": 1, "failed": 1})

    def test_verbose_worker_does_not_deadlock(self):
        cmd = self._worker("import sys; sys.stdout.write('x' * 500000); sys.stderr.write('y' * 500000)")
        self.q.add_task("LOUD", "l")
        hist = dispatch.drain(self.q, dispatch.subprocess_runner(cmd, timeout=30), "disp", 60)
        self.assertEqual(hist, [("LOUD", 1, "done")])
        self.assertEqual(len(self.q.get("LOUD")["result"]["stdout_tail"]), 500)

    def test_lost_lease_kills_worker_and_grandchild_and_is_reassigned(self):
        pidfile = Path(self.tmp.name) / "grandchild.pid"
        cmd = self._worker(f"""
            import subprocess, sys, time
            g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            open({str(pidfile)!r}, "w").write(str(g.pid))
            time.sleep(60)
        """)
        self.q.add_task("L", "l")
        q, clock = self.q, self.clock

        def hb():  # a competing dispatcher took the task: real fencing refusal
            import time
            for _ in range(200):
                if pidfile.exists() and pidfile.read_text():
                    break
                time.sleep(0.05)
            c = state["claim"]
            clock.t += 120
            q.claim("other", 30)
            q.heartbeat(c.task_id, "disp", c.fence, 60)

        state = {}
        inner = dispatch.subprocess_runner(cmd, timeout=20, heartbeat=hb, heartbeat_every=0.5)

        def runner(claim):
            state["claim"] = claim
            return inner(claim)

        hist = dispatch.drain(q, runner, "disp", 60, max_tasks=1)
        self.assertEqual(hist, [("L", 1, "stale")])
        self.assertEqual((q.get("L")["owner"], q.get("L")["fence"]), ("other", 2))
        self.assertIn("stale_refused", [e["kind"] for e in q.events("L")])
        gpid = int(pidfile.read_text())
        import time
        for _ in range(50):
            if not _alive(gpid):
                break
            time.sleep(0.1)
        self.assertFalse(_alive(gpid), "grandchild survived process-group kill")

    def test_non_utf8_output_does_not_turn_success_into_failure(self):
        cmd = self._worker("import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok')")
        self.q.add_task("B", "b")
        hist = dispatch.drain(self.q, dispatch.subprocess_runner(cmd, timeout=30), "disp", 60)
        self.assertEqual(hist, [("B", 1, "done")])

    def test_timeout_is_failed_attempt(self):
        cmd = self._worker("import time; time.sleep(30)")
        self.q.add_task("SLOW", "s", max_attempts=1)
        hist = dispatch.drain(self.q, dispatch.subprocess_runner(cmd, timeout=0.5), "disp", 60)
        self.assertEqual(hist, [("SLOW", 1, "failed->failed")])

    def test_cli_add_run_status(self):
        cmd = self._worker("print('hi')")
        db = str(Path(self.tmp.name) / "cli.sqlite")
        dispatch.main(["add", "--db", db, "--id", "C1", "--title", "c1"])
        dispatch.main(["add", "--db", db, "--id", "C2", "--title", "c2", "--dep", "C1"])
        dispatch.main(["run", "--db", db, "--worker-cmd", " ".join(cmd), "--lease", "30"])
        dispatch.main(["recover", "--db", db])
        dispatch.main(["status", "--db", db])
        q = TaskQueue(db)
        self.assertEqual(q.counts()["done"], 2)
        q.close()

    def test_no_trading_or_network_imports(self):
        for name in ("algobani_queue.py", "algobani_dispatch.py"):
            src = (Path(__file__).resolve().parents[1] / "deploy" / name).read_text()
            for forbidden in ("requests", "urllib", "firestore", "kite", "upstox", "india_trader", "http.client"):
                self.assertNotIn(f"import {forbidden}", src)
                self.assertNotIn(f"from {forbidden}", src)


if __name__ == "__main__":
    unittest.main()
