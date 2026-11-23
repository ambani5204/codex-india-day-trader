"""Synthetic independent-source manifest regressions; no network or private data."""
import unittest
from deploy.phase0_independent_manifests import audit_independent_manifests as audit

J = [{"session_id":"s","run_id":"r","started_at":"2026-11-19T09:15:00+05:30","market_date":"2026-11-19","strategy":"ORB"}]
S = {"kind":"SIGNAL","event_id":"e","session_id":"s","run_id":"r"}

class IndependentManifestTests(unittest.TestCase):
    def test_equal(self):
        self.assertTrue(audit(J, [dict(J[0])], [S], [S])["ok"])
    def test_missing_firestore(self):
        self.assertEqual(audit(J, None, [S], [S])["reason"], "FIRESTORE_MISSING_MANIFEST")
    def test_mismatched_start(self):
        other = [dict(J[0], started_at="2026-11-19T09:16:00+05:30")]
        self.assertEqual(audit(J, other, [S], [S])["reason"], "INDEPENDENT_SESSION_PROVENANCE_MISMATCH")
    def test_mismatched_strategy(self):
        self.assertFalse(audit(J, [dict(J[0], strategy="EMA")], [S], [S])["ok"])
    def test_ambiguous_restart(self):
        other = [J[0], dict(J[0], started_at="2026-11-19T09:16:00+05:30")]
        self.assertEqual(audit(other, J, [S], [S])["reason"], "JOURNAL_AMBIGUOUS_SESSION")
    def test_duplicate(self):
        self.assertEqual(audit(J, J+J, [S], [S])["reason"], "FIRESTORE_DUPLICATE_PROVENANCE")
    def test_event_mismatch(self):
        self.assertEqual(audit(J, J, [S], [dict(S,event_id="other")])["reason"], "EVENT_OR_ACCOUNTING_MISMATCH")
    def test_reused_run_id_across_distinct_sessions_fails_closed(self):
        second = dict(J[0], session_id="s2", started_at="2026-11-19T10:15:00+05:30")
        self.assertEqual(audit(J + [second], J + [second], [S], [S])["reason"], "JOURNAL_REUSED_RUN_ID")
    def test_firestore_only_reused_run_id_fails_closed(self):
        second = dict(J[0], session_id="s2", started_at="2026-11-19T10:15:00+05:30")
        self.assertEqual(audit(J, J + [second], [S], [S])["reason"], "FIRESTORE_REUSED_RUN_ID")
    def test_distinct_run_ids_preserve_event_checks(self):
        second = dict(J[0], session_id="s2", run_id="r2", started_at="2026-11-19T10:15:00+05:30")
        self.assertTrue(audit(J + [second], J + [second], [S], [S])["ok"])
    def test_no_private_ids_in_result(self):
        self.assertNotIn("2026-11-19T09:15:00+05:30", str(audit(J, [dict(J[0], strategy="EMA")], [S], [S])))
if __name__ == "__main__":
    unittest.main()
