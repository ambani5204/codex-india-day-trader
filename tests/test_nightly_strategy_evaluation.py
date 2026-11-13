import datetime as dt
import unittest
from deploy.nightly_strategy_evaluation import evaluate, firestore_field, unpack


class NightlyEvaluationTest(unittest.TestCase):
    def test_verified_metrics_and_no_fabricated_improvement(self):
        rows = [
            {"data_type": "PAPER_SIMULATION", "date_ist": "2026-11-13", "market": "NIFTY",
             "closed_trades": 1, "pnl_coverage": 1, "net_pnl": -1140.12,
             "winning_trades": 0, "losing_trades": 1, "signals_count": 4,
             "rejected_count": 6, "errors_count": 0},
            {"data_type": "PAPER_SIMULATION", "date_ist": "2026-11-13", "market": "SENSEX",
             "closed_trades": 1, "pnl_coverage": 1, "net_pnl": 500.0,
             "winning_trades": 1, "losing_trades": 0, "signals_count": 2,
             "rejected_count": 1, "errors_count": 0},
        ]
        r = evaluate(rows, dt.datetime(2026, 11, 13))
        self.assertEqual(r["net_pnl"], -640.12)
        self.assertEqual(r["win_rate"], 50.0)
        self.assertEqual(r["status"], "EVALUATED")
        self.assertFalse(r["change_verified"])
        self.assertIsNone(r["after_net_pnl"])
        self.assertEqual(r["markets"]["SENSEX"]["net_pnl"], 500.0)
        self.assertEqual(unpack(firestore_field(r["markets"])), r["markets"])

    def test_no_data(self):
        r = evaluate([])
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(r["net_pnl"])
        self.assertIsNone(r["win_rate"])


if __name__ == "__main__":
    unittest.main()
