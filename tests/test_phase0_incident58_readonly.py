"""Synthetic, credential-free regressions for incident #58 GET-only metadata."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import phase0_incident58_readonly as audit


class Reply:
    def __init__(self, url, status=200, data_type="PAPER_SIMULATION",
                 updated="2026-11-23T17:18:28Z"):
        self.status_code = status
        self.payload = {
            "name": url.split("https://firestore.googleapis.com/v1/", 1)[1],
            "updateTime": updated,
            "fields": {"data_type": {"stringValue": data_type}},
        }

    def raise_for_status(self):
        if self.status_code not in (200, 404):
            raise RuntimeError("HTTP failed")

    def json(self):
        return self.payload


class MockSession:
    def __init__(self, absent=None, data_type="PAPER_SIMULATION", updated=None):
        self.urls = []
        self.absent = absent
        self.data_type = data_type
        self.updated = updated

    def get(self, url, timeout):
        self.urls.append((url, timeout))
        if self.absent and url.endswith(self.absent):
            return Reply(url, status=404)
        return Reply(url, data_type=self.data_type,
                     updated=self.updated or "2026-11-23T17:18:28Z")


class Incident58ReadonlyTests(unittest.TestCase):
    def test_reads_four_exact_paths_and_returns_no_document_bodies(self):
        session = MockSession()
        rows = audit.inspect_get_only(session)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["status"] == "PRESENT_MODIFIED_SINCE_INCIDENT" for r in rows))
        self.assertTrue(all(set(r) == {"date", "market", "status"} for r in rows))
        self.assertTrue(all(method == 25 for _, method in session.urls))
        self.assertEqual(
            [url.rsplit("/", 1)[-1] for url, _ in session.urls],
            ["2026-11-13_NIFTY", "2026-11-16_NIFTY",
             "2026-11-19_NIFTY", "2026-11-20_SENSEX"])

    def test_missing_document_fails_closed(self):
        rows = audit.inspect_get_only(MockSession(absent="2026-11-19_NIFTY"))
        self.assertEqual(rows[2]["status"], "MISSING_DOCUMENT")

    def test_old_update_time_does_not_prove_this_incident_write(self):
        rows = audit.inspect_get_only(MockSession(updated="2026-11-20T12:00:00Z"))
        self.assertTrue(all(r["status"] == "PRESENT_OLDER_MODIFICATION" for r in rows))

    def test_wrong_type_and_bad_timestamp_are_not_accepted(self):
        bad_type = audit.inspect_get_only(MockSession(data_type="PROXY_RESEARCH"))
        self.assertEqual(bad_type[0]["status"], "UNVERIFIED_DATA_TYPE")
        bad_time = audit.inspect_get_only(MockSession(updated="not-a-timestamp"))
        self.assertEqual(bad_time[0]["status"], "INVALID_UPDATE_TIMESTAMP")

    def test_cross_project_fails_before_get(self):
        with self.assertRaises(ValueError):
            audit.inspect_get_only(MockSession(), "wrong-project")

    def test_absent_credentials_never_call_broker_or_firestore(self):
        with patch.dict("os.environ", {"FIREBASE_PROJECT_ID": audit.EXPECTED_PROJECT,
                                      "FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET": ""}):
            self.assertEqual(audit.main(), 2)

    def test_source_never_has_firestore_write_transport(self):
        source = Path("deploy/phase0_incident58_readonly.py").read_text()
        for call in (".post(", ".patch(", ".delete(", ".put("):
            self.assertNotIn(call, source)
        self.assertIn("session.get(", source)


if __name__ == "__main__":
    unittest.main()
