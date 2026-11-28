"""Phase 6: durable lease, recovery classification, incident log."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from india_trader import incidents, lease, recovery
from india_trader.core import IST


def T(h, m, s=0):
    return dt.datetime(2026, 11, 30, h, m, s, tzinfo=IST)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.p = self.d / "NIFTY_2026-11-30.lease"

    def test_acquire_then_second_holder_blocked(self):
        ok, l1, took = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#1", T(9, 15))
        self.assertTrue(ok); self.assertFalse(took)
        ok2, cur, _ = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#2", T(9, 16))
        self.assertFalse(ok2)                 # live lease held by wf#1
        self.assertEqual(cur.holder, "wf#1")

    def test_same_holder_renews(self):
        _, l1, _ = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#1", T(9, 15))
        ok, l2, took = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#1", T(9, 20))
        self.assertTrue(ok); self.assertFalse(took)
        self.assertEqual(l1.token, l2.token)  # same acquisition, heartbeat advanced

    def test_stale_lease_taken_over(self):
        lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#1", T(9, 15), lease_seconds=600)
        # 11 minutes later with a 10-min lease -> expired, wf#2 seizes it
        ok, new, took = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#2", T(9, 26))
        self.assertTrue(ok); self.assertTrue(took)
        self.assertEqual(new.holder, "wf#2")

    def test_renew_and_release_require_token(self):
        _, l1, _ = lease.acquire(self.p, "NIFTY", "2026-11-30", "wf#1", T(9, 15))
        self.assertFalse(lease.renew(self.p, "wrong-token", T(9, 16)))
        self.assertTrue(lease.renew(self.p, l1.token, T(9, 16)))
        self.assertFalse(lease.release(self.p, "wrong-token"))
        self.assertTrue(lease.release(self.p, l1.token))
        self.assertFalse(self.p.exists())


class RecoveryTests(unittest.TestCase):
    def _start(self):
        return {"event": "SESSION_START", "session": "s", "market": "NIFTY",
                "capital": 15000, "mode": "paper", "timestamp": T(9, 15).isoformat()}

    def test_clean(self):
        evs = [self._start(), {"event": "SESSION_SUMMARY", "session": "s",
               "market": "NIFTY", "status": "COMPLETE", "summary": {}}]
        r = recovery.classify(evs)
        self.assertEqual(r.state, recovery.CLEAN)
        self.assertFalse(r.can_auto_resume)

    def test_paused_is_auto_resumable(self):
        evs = [self._start(), {"event": "SESSION_PAUSED", "session": "s", "market": "NIFTY"}]
        r = recovery.classify(evs)
        self.assertEqual(r.state, recovery.PAUSED_RESUMABLE)
        self.assertTrue(r.can_auto_resume)

    def test_unresolved_blocks_retry(self):
        evs = [self._start(), {"event": "UNRESOLVED_POSITION", "market": "NIFTY"}]
        r = recovery.classify(evs)
        self.assertEqual(r.state, recovery.UNRESOLVED_NEEDS_RECONCILE)
        self.assertFalse(r.can_auto_resume)

    def test_crash_no_terminal(self):
        evs = [self._start(), {"event": "INDEX_SIGNAL", "market": "NIFTY"}]
        r = recovery.classify(evs)
        self.assertEqual(r.state, recovery.CRASHED_NO_TERMINAL)
        self.assertFalse(r.can_auto_resume)

    def test_unresolved_beats_summary(self):
        evs = [self._start(), {"event": "UNRESOLVED_POSITION", "market": "NIFTY"},
               {"event": "SESSION_SUMMARY", "session": "s", "market": "NIFTY",
                "status": "COMPLETE", "summary": {}}]
        self.assertEqual(recovery.classify(evs).state, recovery.UNRESOLVED_NEEDS_RECONCILE)

    def test_no_session(self):
        self.assertEqual(recovery.classify([]).state, recovery.NO_SESSION)


class IncidentTests(unittest.TestCase):
    def test_append_only_and_read(self):
        p = Path(tempfile.mkdtemp()) / "incidents.jsonl"
        incidents.record(p, incidents.STALE_LEASE_TAKEOVER, market="NIFTY",
                         day="2026-11-30", holder="wf#2", detail="seized expired lease", now=T(9, 26))
        incidents.record(p, incidents.UNRESOLVED_ON_RECOVERY, market="NIFTY",
                         day="2026-11-30", detail="open position found", now=T(9, 27))
        rows = incidents.read_all(p)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kind"], incidents.STALE_LEASE_TAKEOVER)
        self.assertEqual(rows[1]["kind"], incidents.UNRESOLVED_ON_RECOVERY)


if __name__ == "__main__":
    unittest.main()
