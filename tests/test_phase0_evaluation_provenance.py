import unittest
from deploy.phase0_evaluation_provenance import classify_evaluation as classify

class TestEvaluationProvenance(unittest.TestCase):
    def test_saturday_orphan_remains_pending(self):
        x = classify({"report_date": "2026-11-14"}, [], "2026-11-14")
        self.assertEqual(x["status"], "RECONCILIATION_PENDING")
        self.assertIn("WEEKEND_EVALUATION_REQUIRES_PROVENANCE", x["issues"])
    def test_weekday_orphan_remains_pending(self):
        self.assertIn("NO_ELIGIBLE_HISTORY", classify({}, [], "2026-11-13")["issues"])
    def test_matching_run_is_linked(self):
        x = classify({"run_id": "r1"}, [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "run_id": "r1"}], "2026-11-13")
        self.assertEqual(x["status"], "LINKED_BY_RUN_ID")
    def test_wrong_run_fails(self):
        x = classify({"run_id": "r2"}, [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "run_id": "r1"}], "2026-11-13")
        self.assertIn("EVALUATION_RUN_NOT_IN_HISTORY", x["issues"])
    def test_non_paper_not_eligible(self):
        x = classify({"run_id": "r1"}, [{"date_ist": "2026-11-13", "data_type": "PROXY_RESEARCH", "run_id": "r1"}], "2026-11-13")
        self.assertIn("NO_ELIGIBLE_HISTORY", x["issues"])
    def test_unavailable_history_is_unknown(self):
        self.assertEqual(classify({}, None, "2026-11-13")["status"], "UNKNOWN")
    def test_missing_identity_fails(self):
        x = classify({}, [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION"}], "2026-11-13")
        self.assertIn("HISTORY_RUN_ID_MISSING", x["issues"])
        self.assertIn("EVALUATION_RUN_ID_MISSING", x["issues"])

if __name__ == "__main__":
    unittest.main()
