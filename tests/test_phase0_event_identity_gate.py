"""Synthetic fail-closed event identity cases. Offline only."""
import unittest
from deploy.phase0_event_identity_gate import compare_event_identity as compare

def records(s="s1", t="t1", session="r1"):
    return [{"event":"INDEX_SIGNAL","signal_id":s},
            {"event":"PAPER_TRADE_CLOSED","trade_id":t},
            {"event":"SESSION_SUMMARY","session_id":session}]

class EventIdentityGateTests(unittest.TestCase):
    def test_missing_independent_manifest_blocks(self):
        self.assertEqual(compare(records()), "FIRESTORE_EVENT_MANIFEST_MISSING")
    def test_same_counts_different_identities_block(self):
        self.assertEqual(compare(records(), records("s2","t2"), True), "EVENT_IDENTITY_MISMATCH")
    def test_duplicate_archive_trade_id_blocks(self):
        a=records()
        a.insert(2,dict(a[1]))
        self.assertEqual(compare(a,a,True), "REPEATED_EVENT_ID")
    def test_duplicate_firestore_trade_id_blocks(self):
        b=records()
        b.insert(2,dict(b[1]))
        self.assertEqual(compare(records(),b,True), "FIRESTORE_REPEATED_EVENT_ID")
    def test_missing_id_blocks(self):
        a=records()
        del a[1]["trade_id"]
        self.assertEqual(compare(a,records(),True), "MISSING_OR_INVALID_ID")
    def test_matching_ids_not_restart_proof(self):
        self.assertEqual(compare(records(),records()), "RESTART_PROVENANCE_UNVERIFIED")
    def test_attested_match_only_when_explicit(self):
        self.assertEqual(compare(records(),records(),True), "EVENT_IDENTITIES_MATCH_PROVENANCE_ATTESTED")
    def test_whitespace_is_not_silent_normalization(self):
        self.assertEqual(compare(records(" s1"),records(),True), "MISSING_OR_INVALID_ID")

if __name__ == "__main__":
    unittest.main()
