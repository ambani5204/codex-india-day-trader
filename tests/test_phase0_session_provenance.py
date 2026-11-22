"""Synthetic tests only: no credentials, external access or private records."""
import unittest
from deploy.phase0_session_provenance import audit_session_provenance

A = dict(session_id="s1", run_id="r1", market_date="2026-11-19", market="NIFTY", started_at="09:15")
B = dict(session_id="s2", run_id="r2", market_date="2026-11-19", market="SENSEX", started_at="09:15")

class ProvenanceTests(unittest.TestCase):
    def test_match(self):
        self.assertTrue(audit_session_provenance([A, B], [B, A])["ok"])
    def test_missing_source(self):
        self.assertEqual(audit_session_provenance([A], None)["reason"], "MISSING_INDEPENDENT_MANIFEST")
    def test_identity_mismatch(self):
        self.assertEqual(audit_session_provenance([A], [B])["reason"], "SESSION_PROVENANCE_MISMATCH")
    def test_duplicate(self):
        self.assertEqual(audit_session_provenance([A, A], [A])["reason"], "JOURNAL_DUPLICATE_PROVENANCE_RECORD")
    def test_restart_collision(self):
        self.assertEqual(audit_session_provenance([A, dict(A, run_id="r3")], [A])["reason"], "JOURNAL_AMBIGUOUS_SESSION_RESTART")
    def test_missing_field(self):
        self.assertEqual(audit_session_provenance([dict(A, started_at="")], [A])["reason"], "JOURNAL_MISSING_PROVENANCE_FIELD")
    def test_no_private_identifiers_in_output(self):
        self.assertNotIn("s1", str(audit_session_provenance([A], [B])))
if __name__ == "__main__":
    unittest.main()
