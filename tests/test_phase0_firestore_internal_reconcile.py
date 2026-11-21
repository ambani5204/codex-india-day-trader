"""Pure synthetic invariant tests for live Firestore read models."""
import unittest

from deploy.phase0_firestore_internal_reconcile import (
    validate_day, compare_latest, compare_evaluation,
)


def snapshot(**extra):
    row = {
        "data_type": "PAPER_SIMULATION",
        "date_ist": "2026-11-19",
        "market": "NIFTY",
        "run_id": "test",
        "closed_trades": 1,
        "pnl_coverage": 1,
        "signals_count": 2,
        "entry_event_count": 1,
        "net_pnl": -12.0,
        "gross_pnl": -10.0,
        "fees_total": 2.0,
        "strategy_stats": {
            "MEAN_REVERSION": {
                "closed_trades": 1, "verified_trades": 1, "net_pnl": -12.0
            }
        },
    }
    row.update(extra)
    return row


class FirestoreInternalReconcileTests(unittest.TestCase):
    def test_consistent_single_trade_passes(self):
        self.assertEqual(validate_day(snapshot()), "MATCH")

    def test_known_31_trade_cap_rejected(self):
        stat = {"MEAN_REVERSION": {"closed_trades": 30,
                "verified_trades": 30, "net_pnl": -360.0}}
        result = snapshot(closed_trades=31, pnl_coverage=31,
                          net_pnl=-372.0, strategy_stats=stat)
        self.assertEqual(validate_day(result), "STRATEGY_COUNT_MISMATCH")

    def test_missing_financial_coverage_is_not_verified_zero(self):
        result = snapshot(closed_trades=1, pnl_coverage=0, net_pnl=None)
        self.assertEqual(validate_day(result), "PARTIAL_FINANCIAL_COVERAGE")

    def test_latest_mismatched_pnl_fails(self):
        self.assertEqual(compare_latest(snapshot(), snapshot(net_pnl=-13.0)),
                         "LATEST_HISTORY_FIELD_MISMATCH_NET_PNL")

    def test_date_evaluation_matches_verified_pnl(self):
        history = snapshot()
        report = {"closed_trades": 1, "verified_pnl_trades": 1, "net_pnl": -12.0}
        self.assertEqual(compare_evaluation(report, [history]), "MATCH")
        self.assertEqual(compare_evaluation({**report, "net_pnl": -9.0},
                                            [history]), "EVALUATION_NET_MISMATCH")

    def test_null_pnl_is_correct_for_zero_closed_market(self):
        nifty = snapshot()
        sensex = snapshot(market="SENSEX", closed_trades=0,
                          pnl_coverage=0, net_pnl=None, strategy_stats={})
        report = {"closed_trades": 1, "verified_pnl_trades": 1, "net_pnl": -12.0}
        self.assertEqual(compare_evaluation(report, [nifty, sensex]), "MATCH")

    def test_truly_partial_financial_coverage_remains_blocked(self):
        unknown = snapshot(market="SENSEX", closed_trades=1,
                           pnl_coverage=0, net_pnl=None, strategy_stats={})
        report = {"closed_trades": 2, "verified_pnl_trades": 1, "net_pnl": -12.0}
        self.assertEqual(compare_evaluation(report, [snapshot(), unknown]),
                         "EVALUATION_PARTIAL_FINANCIAL_COVERAGE")

    def test_empty_date_is_not_healthy(self):
        self.assertEqual(compare_evaluation({}, []), "NO_HISTORY_FOR_DATE")

    def test_bad_count_is_not_silently_zero(self):
        bad = snapshot(closed_trades=None)
        self.assertEqual(validate_day(bad), "MISSING_COVERAGE_COUNTER")


if __name__ == "__main__":
    unittest.main()
