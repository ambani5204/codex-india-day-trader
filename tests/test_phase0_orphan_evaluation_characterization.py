"""Phase 0 synthetic characterization of orphan evaluation and coverage safety.

Audit-only: these tests document current behavior; no production Firestore
documents, private archives or financial values are accessed.
"""
import unittest

from deploy.phase0_firestore_internal_reconcile import (
    compare_evaluation, validate_day, comparable,
)


class EvaluationOrphanCharacterization(unittest.TestCase):
    def test_weekend_evaluation_without_eligible_history_fails_closed(self):
        report = {"report_date": "2026-11-14", "closed_trades": 0,
                  "verified_pnl_trades": 0, "net_pnl": None}
        self.assertEqual(compare_evaluation(report, []), "NO_HISTORY_FOR_DATE")

    def test_empty_weekday_history_also_fails_closed(self):
        report = {"report_date": "2026-11-16", "closed_trades": 0,
                  "verified_pnl_trades": 0, "net_pnl": None}
        self.assertEqual(compare_evaluation(report, []), "NO_HISTORY_FOR_DATE")

    def test_missing_history_is_not_a_zero_trade_session(self):
        report = {"closed_trades": 0, "verified_pnl_trades": 0, "net_pnl": None}
        self.assertNotEqual(compare_evaluation(report, []), "MATCH")

    def test_history_rejects_boolean_coverage_counter(self):
        row = {"data_type": "PAPER_SIMULATION", "closed_trades": True,
               "pnl_coverage": 0}
        self.assertEqual(validate_day(row), "MISSING_COVERAGE_COUNTER")

    def test_exact_string_session_identity_not_implicitly_numeric(self):
        self.assertFalse(comparable("run-1", "run-2"))


if __name__ == "__main__":
    unittest.main()
