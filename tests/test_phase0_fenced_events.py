"""Offline atomic writer integration tests: CAS lease and immutable CE/PE events.

A deterministic in-memory fake applies all Firestore writes or none. No
credentials, real Firestore requests, broker orders or historical data.
"""
from __future__ import annotations

import copy
import datetime as dt
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from deploy import phase0_fenced_events as writer
from deploy import phase0_session_lease as lease

NOW = dt.datetime(2026, 11, 23, 10, 0, tzinfo=lease.IST)
DAY = "2026-11-23"
OCCURRED = "2026-11-23T04:30:01.000000Z"


class Reply:
    def __init__(self, code, content=None):
        self.status_code = code
        self.content = copy.deepcopy(content or {})

    def json(self):
        return copy.deepcopy(self.content)


class AtomicFakeFirestore:
    """Exactly emulates affected existence/updateTime preconditions atomically."""
    def __init__(self):
        self.documents = {}
        self.lock = threading.Lock()
        self.writes = 0
        self.version = 0
        self.ack_lost = False
        self.malformed_ack = False
        self.fail_next_code = None

    def get(self, url, timeout):
        if not url.startswith("https://firestore.googleapis.com/v1/" + lease.DB_RESOURCE):
            raise AssertionError("Unauthorized URL")
        assert timeout == 25
        name = url.split("https://firestore.googleapis.com/v1/", 1)[1]
        with self.lock:
            if name not in self.documents:
                return Reply(404)
            return Reply(200, self.documents[name])

    def post(self, url, json, timeout):
        if url != lease.API_ROOT + "/documents:commit" or timeout != 25:
            raise AssertionError("Only atomic Firestore commit permitted")
        with self.lock:
            if self.fail_next_code is not None:
                code = self.fail_next_code
                self.fail_next_code = None
                return Reply(code)
            writes = json.get("writes", [])
            if not writes or len(writes) > 2:
                raise AssertionError("Invalid write batch")
            for entry in writes:
                if set(entry) != {"update", "currentDocument"}:
                    raise AssertionError("No delete/transform allowed")
                name = entry["update"]["name"]
                if not name.startswith(lease.DB_RESOURCE + "/documents/"):
                    raise AssertionError("Unexpected project")
                old = self.documents.get(name)
                condition = entry["currentDocument"]
                if condition == {"exists": False}:
                    if old is not None:
                        return Reply(409)
                elif set(condition) == {"updateTime"}:
                    if old is None or old.get("updateTime") != condition["updateTime"]:
                        return Reply(409)
                else:
                    raise AssertionError("Unconditional Firestore write")
            # Apply the complete batch only after every precondition succeeded.
            response = []
            for entry in writes:
                self.version += 1
                stamp = "2026-11-23T04:30:%02d.000000Z" % self.version
                doc = copy.deepcopy(entry["update"])
                doc["updateTime"] = stamp
                self.documents[doc["name"]] = doc
                response.append({"updateTime": stamp})
                self.writes += 1
            if self.ack_lost:
                raise ConnectionError("Synthetic disconnect AFTER atomic commit")
            return Reply(200, {"writeResults": ([{}] if self.malformed_ack
                                                else response)})


def sample_event(**changes):
    data = {
        "event_id": "signal-s1-entry-001",
        "event_kind": "PAPER_BUY_FILLED",
        "date_ist": DAY,
        "market": "NIFTY",
        "session_id": "20261123_NIFTY_v1",
        "strategy_id": "MEAN_REVERSION",
        "strategy_version": "v1",
        "instrument_key": "NSE_FO|12345",
        "option_type": "CE",
        "quantity": 65,
        "fill_price": 110.5,
        "occurred_at": OCCURRED,
    }
    data.update(changes)
    return writer.PaperEvent(**data)


class FencedPaperEventTests(unittest.TestCase):
    def setUp(self):
        self.db = AtomicFakeFirestore()
        self.current = lease.acquire(self.db, DAY, "NIFTY", "run-100",
                                     "v1", now=NOW)
        self.assertEqual(self.db.writes, 1)

    def commit(self, event=None, delta=5, owned=None):
        return writer.append_once(self.db, owned or self.current,
                                  event or sample_event(),
                                  now=NOW + dt.timedelta(seconds=delta))

    def test_lease_and_one_immutable_option_fill_commit_atomically(self):
        old_version = self.current.update_time
        next_owner = self.commit()
        self.assertNotEqual(old_version, next_owner.update_time)
        self.assertEqual(self.db.writes, 3)
        doc = self.db.documents[writer._event_name(sample_event())]
        fields = doc["fields"]
        self.assertEqual(fields["paper_only"]["booleanValue"], True)
        self.assertEqual(fields["market"]["stringValue"], "NIFTY")
        self.assertEqual(fields["option_type"]["stringValue"], "CE")
        self.assertEqual(fields["quantity"]["integerValue"], "65")
        self.assertEqual(fields["owner_attempt_id"]["stringValue"], "run-100")
        self.assertEqual(fields["lease_id"]["stringValue"], self.current.lease_id)
        self.assertIsNone(fields["net_pnl"]["nullValue"])

    def test_same_immutable_event_id_does_not_duplicate_on_replay(self):
        self.current = self.commit()
        with self.assertRaisesRegex(writer.EventRejected,
                                    "FENCED_EVENT_CAS_OR_DUPLICATE_CONFLICT"):
            self.commit(delta=10)
        self.assertEqual(self.db.writes, 3)
        self.assertEqual(len(self.db.documents), 2)

    def test_two_concurrent_same_owner_events_require_one_cas_winner(self):
        def attempt(i):
            try:
                return self.commit(event=sample_event(event_id="entry-" + str(i)),
                                   delta=8)
            except writer.EventRejected:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(lease_result is not None for lease_result in outcomes), 1)
        self.assertEqual(self.db.writes, 3)
        self.assertEqual(len(self.db.documents), 2)

    def test_stale_lease_fence_cannot_append_any_different_event(self):
        stale = self.current
        self.current = self.commit()
        with self.assertRaisesRegex(writer.EventRejected, "LOST_FENCE"):
            self.commit(sample_event(event_id="another-valid-event"), owned=stale)
        self.assertEqual(self.db.writes, 3)

    def test_expired_or_near_expired_lease_rejects_without_write(self):
        with self.assertRaisesRegex(writer.EventRejected, "LEASE_TOO_CLOSE_TO_EXPIRY"):
            self.commit(delta=111)
        with self.assertRaisesRegex(writer.EventRejected, "LEASE_TOO_CLOSE_TO_EXPIRY"):
            self.commit(delta=121)
        self.assertEqual(self.db.writes, 1)

    def test_deleted_or_wrong_owner_lease_blocks(self):
        name = lease.document_name(DAY, "NIFTY")
        doc = self.db.documents.pop(name)
        with self.assertRaisesRegex(writer.EventRejected, "NO_CANONICAL_LEASE"):
            self.commit()
        self.db.documents[name] = doc
        doc["fields"]["owner_attempt_id"]["stringValue"] = "other-owner"
        with self.assertRaisesRegex(writer.EventRejected, "LOST_FENCE"):
            self.commit()
        self.assertEqual(self.db.writes, 1)

    def test_conflicting_external_cas_does_not_create_orphan_event(self):
        self.db.fail_next_code = 409
        with self.assertRaisesRegex(writer.EventRejected, "CAS_OR_DUPLICATE"):
            self.commit()
        self.assertEqual(self.db.writes, 1)
        self.assertEqual(len(self.db.documents), 1)

    def test_lost_ack_after_success_is_ambiguous_and_cannot_blind_retry(self):
        self.db.ack_lost = True
        with self.assertRaisesRegex(lease.LeaseUnavailable,
                                    "FENCED_EVENT_COMMIT_UNKNOWN"):
            self.commit()
        self.db.ack_lost = False
        self.assertEqual(self.db.writes, 3)   # Server did commit.
        with self.assertRaisesRegex(writer.EventRejected, "LOST_FENCE"):
            self.commit()
        self.assertEqual(self.db.writes, 3)

    def test_get_only_recovery_proves_original_event_after_lost_ack(self):
        original = sample_event()
        self.db.ack_lost = True
        with self.assertRaisesRegex(lease.LeaseUnavailable, "FENCED_EVENT_COMMIT_UNKNOWN"):
            self.commit(original)
        self.db.ack_lost = False
        self.assertEqual(writer.verify_persisted_event(self.db, self.current, original),
                         "EVENT_PERSISTED_EXACT_MATCH")
        self.assertEqual(self.db.writes, 3)  # GET cannot publish a second fill.

    def test_get_only_recovery_distinguishes_missing_from_success(self):
        result = writer.verify_persisted_event(self.db, self.current, sample_event())
        self.assertEqual(result, "EVENT_ABSENT_UNVERIFIED")
        self.assertEqual(self.db.writes, 1)

    def test_get_only_recovery_rejects_conflicting_payload_identity(self):
        self.commit()
        altered = sample_event(fill_price=999.0)
        with self.assertRaisesRegex(writer.EventRejected, "EVENT_SOURCE_LINEAGE_OR_PAYLOAD_MISMATCH"):
            writer.verify_persisted_event(self.db, self.current, altered)
        self.assertEqual(self.db.writes, 3)

    def test_get_only_recovery_rejects_malformed_document(self):
        event = sample_event()
        self.commit(event)
        name = writer._event_name(event)
        self.db.documents[name]["fields"].pop("owner_attempt_id")
        with self.assertRaisesRegex(writer.EventRejected, "EVENT_SOURCE_LINEAGE_OR_PAYLOAD_MISMATCH"):
            writer.verify_persisted_event(self.db, self.current, event)

    def test_get_only_recovery_never_calls_write_on_read_failure(self):
        class Offline:
            def get(self, url, timeout):
                raise ConnectionError("Synthetic outage")
        with self.assertRaisesRegex(lease.LeaseUnavailable, "EVENT_READ_UNAVAILABLE"):
            writer.verify_persisted_event(Offline(), self.current, sample_event())
        self.assertEqual(self.db.writes, 1)

    def test_malformed_ack_cannot_be_reported_as_success(self):
        self.db.malformed_ack = True
        with self.assertRaisesRegex(lease.LeaseUnavailable,
                                    "FENCED_EVENT_ACK_UNVERIFIED"):
            self.commit()
        self.assertEqual(self.db.writes, 3)

    def test_valid_close_requires_after_cost_pnl_and_open_event(self):
        close = sample_event(
            event_id="trade-close-001", event_kind="PAPER_TRADE_CLOSED",
            open_event_id="signal-s1-entry-001", gross_pnl=975.0,
            fees_total=75.0, net_pnl=900.0, fill_price=125.5)
        self.current = self.commit(sample_event())
        self.current = self.commit(close, delta=11)
        self.assertEqual(self.db.writes, 5)
        event_doc = self.db.documents[writer._event_name(close)]
        self.assertEqual(event_doc["fields"]["net_pnl"]["doubleValue"], 900.0)
        self.assertEqual(event_doc["fields"]["fees_total"]["doubleValue"], 75.0)

    def test_missing_or_inaccurate_financial_coverage_blocks_close(self):
        for overrides in (
            {"net_pnl": None},
            {"fees_total": None},
            {"gross_pnl": None},
            {"fees_total": -1},
            {"net_pnl": 900.5},
            {"net_pnl": float("nan")},
            {"net_pnl": float("inf")},
            {"open_event_id": ""},
        ):
            with self.subTest(overrides=overrides):
                fields = {
                    "event_id": "close-002", "event_kind": "PAPER_TRADE_CLOSED",
                    "open_event_id": "entry-001", "gross_pnl": 975.0,
                    "fees_total": 75.0, "net_pnl": 900.0,
                }
                fields.update(overrides)
                event = sample_event(**fields)
                with self.assertRaises(writer.EventRejected):
                    self.commit(event)
        self.assertEqual(self.db.writes, 1)

    def test_raw_index_signal_and_unqualified_contract_blocked(self):
        cases = [
            {"event_kind": "INDEX_SIGNAL"},
            {"option_type": "INDEX"},
            {"instrument_key": ""},
            {"quantity": 0},
            {"fill_price": 0.0},
            {"fill_price": float("nan")},
            {"event_id": "../unsafe"},
            {"occurred_at": "2026-11-22T04:30:01.000000Z"},
            {"strategy_version": "v2"},
            {"market": "SENSEX"},
            {"date_ist": "2026-11-20"},
            {"net_pnl": 500.0},  # Entry cannot claim closed after-cost profit.
        ]
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(writer.EventRejected):
                self.commit(sample_event(**updates))
        self.assertEqual(self.db.writes, 1)

    def test_credit_spread_requires_distinct_hedge_instrument(self):
        credit = sample_event(event_kind="PAPER_SPREAD_OPEN", option_type="PE",
                              hedge_instrument_key="NSE_FO|67890")
        self.current = self.commit(credit)
        self.assertEqual(self.db.writes, 3)
        with self.assertRaises(writer.EventRejected):
            self.commit(sample_event(event_id="credit-bad", event_kind="PAPER_SPREAD_OPEN",
                                     hedge_instrument_key="NSE_FO|12345"), delta=10)

    def test_legacy_workers_publishers_have_not_been_silently_wired(self):
        source = Path("deploy/phase0_fenced_events.py").read_text()
        self.assertNotIn("google.auth", source)
        self.assertNotIn("session.patch", source)
        self.assertNotIn("session.delete", source)
        for path in ("deploy/firebase_live_publisher.py",
                     "deploy/cloud_paper_session.py",
                     ".github/workflows/cloud-ce-pe-paper.yml",
                     "india_trader/advanced_forward.py"):
            with self.subTest(path=path):
                self.assertNotIn("phase0_fenced_events", Path(path).read_text())


if __name__ == "__main__":
    unittest.main()
