"""Credential-free Phase 0 Firestore CAS paper-session lease regression suite."""
from __future__ import annotations

import copy
import datetime as dt
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from deploy import phase0_session_lease as lease


NOW = dt.datetime(2026, 11, 23, 10, 0, tzinfo=lease.IST)
DAY = "2026-11-23"


class Reply:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.payload = payload or {}

    def json(self):
        return copy.deepcopy(self.payload)


class InMemoryFirestore:
    """Emulates Firestore's atomic currentDocument preconditions, never network."""
    def __init__(self):
        self.doc = None
        self.counter = 0
        self.lock = threading.Lock()
        self.write_count = 0
        self.before_commit = None
        self.malformed_ack = False

    def get(self, url, timeout):
        self.check_url(url)
        self.assert_timeout(timeout)
        with self.lock:
            if self.doc is None:
                return Reply(404)
            if url != "https://firestore.googleapis.com/v1/" + self.doc["name"]:
                return Reply(404)
            return Reply(200, self.doc)

    def post(self, url, json, timeout):
        if url != lease.API_ROOT + "/documents:commit" or timeout != 25:
            raise AssertionError("Unexpected Firestore endpoint")
        writes = json.get("writes", [])
        if len(writes) != 1 or "update" not in writes[0]:
            raise AssertionError("Expected one atomic update")
        if any(x in writes[0] for x in ("delete", "transform")):
            raise AssertionError("Destructive/non-CAS write")
        if self.before_commit:
            hook = self.before_commit
            self.before_commit = None
            hook(self)
        write = writes[0]
        with self.lock:
            condition = write.get("currentDocument")
            if condition == {"exists": False}:
                if self.doc is not None:
                    return Reply(409)
            elif set(condition or {}) == {"updateTime"}:
                if self.doc is None or self.doc.get("updateTime") != condition["updateTime"]:
                    return Reply(409)
            else:
                raise AssertionError("Unconditional write was attempted")
            self.counter += 1
            timestamp = "2026-11-23T04:30:%02d.000000Z" % self.counter
            self.doc = copy.deepcopy(write["update"])
            self.doc["updateTime"] = timestamp
            self.write_count += 1
            if self.malformed_ack:
                return Reply(200, {"writeResults": [{}]})
            return Reply(200, {"writeResults": [{"updateTime": timestamp}]})

    @staticmethod
    def check_url(url):
        if not url.startswith("https://firestore.googleapis.com/v1/" + lease.DB_RESOURCE + "/documents/"):
            raise AssertionError("Unexpected project/database URL")

    @staticmethod
    def assert_timeout(timeout):
        if timeout != 25:
            raise AssertionError("Unexpected timeout")


class SessionLeaseTests(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryFirestore()

    def acquire(self, owner="run-100", version="strategy_v1", db=None):
        return lease.acquire(db or self.db, DAY, "NIFTY", owner, version, now=NOW)

    def test_atomic_one_winner_of_eight_parallel_starts(self):
        def attempt(i):
            try:
                return self.acquire("run-" + str(i))
            except lease.LeaseBlocked:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.db.write_count, 1)
        self.assertEqual(winners[0].generation, 1)
        self.assertEqual(winners[0].state, "ACTIVE")

    def test_canonical_document_key_ignores_attempt_and_strategy(self):
        a = lease.document_name(DAY, "NIFTY")
        self.assertTrue(a.endswith("paper_session_leases_v1/2026-11-23_NIFTY"))
        current = self.acquire()
        with self.assertRaisesRegex(lease.LeaseBlocked, "CAS_CONFLICT"):
            self.acquire("run-200", "strategy_v2")
        self.assertEqual(lease.inspect(self.db, DAY, "NIFTY"), current)

    def test_canonical_keys_are_distinct_between_markets(self):
        nifty = lease.document_name(DAY, "NIFTY")
        sensex = lease.document_name(DAY, "SENSEX")
        self.assertNotEqual(nifty, sensex)
        self.assertTrue(nifty.endswith("_NIFTY"))
        self.assertTrue(sensex.endswith("_SENSEX"))

    def test_only_current_owner_can_renew_with_cas(self):
        first = self.acquire()
        later = NOW + dt.timedelta(seconds=20)
        renewed = lease.heartbeat(self.db, first, now=later)
        self.assertEqual(renewed.lease_id, first.lease_id)
        self.assertEqual(renewed.generation, 1)
        self.assertNotEqual(renewed.update_time, first.update_time)
        with self.assertRaisesRegex(lease.LeaseBlocked, "LOST_FENCE_OR_STALE_READ"):
            lease.heartbeat(self.db, first, now=later)

    def test_expired_owner_cannot_renew_or_automatically_takeover(self):
        first = self.acquire()
        with self.assertRaisesRegex(lease.LeaseBlocked, "LEASE_EXPIRED"):
            lease.heartbeat(self.db, first, now=NOW + dt.timedelta(seconds=121))
        with self.assertRaisesRegex(lease.LeaseBlocked, "CAS_CONFLICT"):
            self.acquire("run-after-crash")
        with self.assertRaisesRegex(lease.LeaseBlocked, "RECONCILIATION"):
            lease.deny_automatic_takeover()
        self.assertEqual(self.db.write_count, 1)

    def test_interleaved_heartbeat_remote_write_causes_cas_conflict(self):
        first = self.acquire()
        def unrelated_writer(db):
            # Simulates a competing writer modifying the same exact doc after GET.
            db.counter += 1
            db.doc["updateTime"] = "2026-11-23T04:30:55.000000Z"
        self.db.before_commit = unrelated_writer
        with self.assertRaisesRegex(lease.LeaseBlocked, "CAS_CONFLICT"):
            lease.heartbeat(self.db, first, now=NOW + dt.timedelta(seconds=10))
        self.assertEqual(self.db.write_count, 1)

    def test_response_unknown_fails_closed_even_if_commit_occurred(self):
        self.db.malformed_ack = True
        with self.assertRaisesRegex(lease.LeaseUnavailable, "COMMIT_ACK_UNVERIFIED"):
            self.acquire()
        self.assertEqual(self.db.write_count, 1)
        self.db.malformed_ack = False
        with self.assertRaisesRegex(lease.LeaseBlocked, "CAS_CONFLICT"):
            self.acquire("different")
        self.assertEqual(self.db.write_count, 1)

    def test_unavailable_read_never_means_no_owner(self):
        class Offline:
            def get(self, url, timeout):
                raise ConnectionError("Synthetic lost network")
        with self.assertRaisesRegex(lease.LeaseUnavailable, "LEASE_READ_FAILED"):
            lease.inspect(Offline(), DAY, "NIFTY")

    def test_malformed_remote_metadata_blocks_renew(self):
        item = self.acquire()
        self.db.doc["fields"]["owner_attempt_id"] = {"integerValue": "10"}
        with self.assertRaises(lease.LeaseBlocked):
            lease.heartbeat(self.db, item, now=NOW + dt.timedelta(seconds=10))
        self.assertEqual(self.db.write_count, 1)

    def test_clock_regression_blocks_renew(self):
        item = self.acquire()
        with self.assertRaisesRegex(lease.LeaseBlocked, "CLOCK_REGRESSION"):
            lease.heartbeat(self.db, item, now=NOW - dt.timedelta(seconds=1))

    def test_date_market_ttl_and_version_validation(self):
        for day in ("2026-02-30", "2026-1-2", "../2026-11-23"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                lease.document_name(day, "NIFTY")
        for market in ("NFO", "NIFTY/../X", ""):
            with self.subTest(market=market), self.assertRaises(ValueError):
                lease.document_name(DAY, market)
        for ttl in (0, 30, 301, True, 1.5):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                lease.acquire(self.db, DAY, "NIFTY", "run-10", "v1", now=NOW,
                              ttl_seconds=ttl)
        with self.assertRaises(ValueError):
            self.acquire(version="../../invalid")
        with self.assertRaises(ValueError):
            lease.acquire(self.db, DAY, "NIFTY", "run", "v1",
                          now=dt.datetime(2026, 11, 23, 10, 0))  # naive
        self.assertEqual(self.db.write_count, 0)

    def test_not_current_ist_date_fails_closed(self):
        with self.assertRaisesRegex(lease.LeaseBlocked, "NOT_CURRENT"):
            lease.acquire(self.db, "2026-11-20", "NIFTY", "run", "v1", now=NOW)
        self.assertEqual(self.db.write_count, 0)

    def test_prototype_never_imported_or_triggered_by_trading_workflow(self):
        from pathlib import Path
        paths = (
            "deploy/cloud_paper_session.py",
            "deploy/cloud_session_gate.py",
            ".github/workflows/cloud-ce-pe-paper.yml",
            "deploy/firebase_live_publisher.py",
        )
        for path in paths:
            with self.subTest(path=path):
                source = Path(path).read_text()
                self.assertNotIn("phase0_session_lease", source)
        source = Path("deploy/phase0_session_lease.py").read_text()
        self.assertNotIn("google.oauth", source)
        self.assertNotIn("def main(", source)
        self.assertNotIn("session.delete(", source)


if __name__ == "__main__":
    unittest.main()
