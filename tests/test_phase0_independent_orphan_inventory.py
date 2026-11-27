"""Synthetic offline tests; no Firestore/private journal access."""
import unittest
from deploy.phase0_firestore_internal_reconcile import count_unmatched_evaluations


class IndependentOrphanInventoryTests(unittest.TestCase):
    def test_duplicate_sessions_do_not_hide_orphan(self):
        history = [
            {"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "session_id": "a"},
            {"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "session_id": "b"},
        ]
        reports = [
            ("latest", {"report_date": "2026-11-14"}),
            ("private-doc-id", {"report_date": "2026-11-14"}),
            ("other-private-id", {"report_date": "2026-11-13"}),
        ]
        result = count_unmatched_evaluations(reports, history)
        self.assertEqual(result, {"missing_eligible_history": 1, "invalid_report_metadata": 0})
        self.assertNotIn("private", str(result))

    def test_missing_report_date_is_not_assumed_orphan(self):
        result = count_unmatched_evaluations([("private", {}), ("private2", {"report_date": None})], [])
        self.assertEqual(result, {"missing_eligible_history": 0, "invalid_report_metadata": 2})

    def test_proxy_history_not_eligible(self):
        history = [{"date_ist": "2026-11-14", "data_type": "PROXY_RESEARCH"}]
        result = count_unmatched_evaluations([("x", {"report_date": "2026-11-14"})], history)
        self.assertEqual(result["missing_eligible_history"], 1)


if __name__ == "__main__":
    unittest.main()
