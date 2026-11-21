"""Synthetic, offline tests; no private trade or Firestore data."""
import unittest
from deploy.phase0_duplicate_provenance import classify_history_groups, classify_orphan_evaluation


class ProvenanceTests(unittest.TestCase):
    def test_distinct_sessions_remain_unverified_and_private(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY", "session_id": "private-A"},
            {"date_ist": "2026-11-19", "market": "NIFTY", "session_id": "private-B"},
        ]
        result = classify_history_groups(rows)
        self.assertEqual(result["duplicate_groups"], 1)
        self.assertEqual(result["distinct_session_groups"], 1)
        self.assertEqual(result["unverified_groups"], 1)
        self.assertNotIn("private-", str(result))

    def test_repeated_and_missing_identity(self):
        rows = [{"date_ist": "2026-11-19", "market": "NIFTY", "session_id": "secret"}] * 2
        rows.append({"date_ist": "2026-11-19", "market": "NIFTY"})
        result = classify_history_groups(rows)
        self.assertEqual(result["repeated_session_identity"], 1)
        self.assertEqual(result["missing_session_identity"], 1)
        self.assertEqual(result["distinct_session_groups"], 0)

    def test_nonduplicates_and_other_markets_ignored(self):
        rows = [
            {"date_ist": "2026-11-19", "market": "NIFTY"},
            {"date_ist": "2026-11-19", "market": "SENSEX"},
            {"date_ist": "2026-11-19", "market": "UNKNOWN"},
        ]
        self.assertEqual(classify_history_groups(rows)["duplicate_groups"], 0)

    def test_weekend_orphan_is_not_auto_resolved(self):
        self.assertEqual(classify_orphan_evaluation("2026-11-14", [], {"run_id": "private"}),
                         "NO_ELIGIBLE_HISTORY_WEEKEND")

    def test_weekday_orphan(self):
        self.assertEqual(classify_orphan_evaluation("2026-11-13", [], {}),
                         "NO_ELIGIBLE_HISTORY")

    def test_missing_run_identity_fails_closed(self):
        histories = [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION"}]
        self.assertEqual(classify_orphan_evaluation("2026-11-13", histories, {}),
                         "MISSING_RUN_PROVENANCE")

    def test_mismatched_run_identity_fails_closed(self):
        histories = [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "run_id": "a"}]
        self.assertEqual(classify_orphan_evaluation("2026-11-13", histories, {"run_id": "b"}),
                         "RUN_PROVENANCE_MISMATCH")

    def test_matching_run_is_not_terminal_proof(self):
        histories = [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "run_id": "a"}]
        self.assertEqual(classify_orphan_evaluation("2026-11-13", histories, {"run_id": "a"}),
                         "IDENTITY_MATCH_TERMINATION_UNVERIFIED")

    def test_duplicate_history_blocks_provenance(self):
        histories = [{"date_ist": "2026-11-13", "data_type": "PAPER_SIMULATION", "run_id": "a"}] * 2
        self.assertEqual(classify_orphan_evaluation("2026-11-13", histories, {"run_id": "a"}),
                         "AMBIGUOUS_HISTORY")

    def test_invalid_date(self):
        self.assertEqual(classify_orphan_evaluation("bad-date", [], {}),
                         "INVALID_REPORT_DATE")


if __name__ == "__main__":
    unittest.main()
