"""Phase-0 audit probes: synthetic events, no broker calls or real orders.

The expectedFailure tracks a *known unfixed bug*. CI success with an expected
failure is evidence of that defect, NOT a successful fix or qualification.
Remove expectedFailure only in a separate, preregistered and tested repair PR.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import firebase_live_publisher as publisher


class AuditStrategyAggregationTest(unittest.TestCase):
    DAY = "2026-11-19"

    def snapshot_with_synthetic_closed_trades(self, count):
        with tempfile.TemporaryDirectory() as folder:
            events = []
            for index in range(count):
                minute = index % 60
                hour = 10 + index // 60
                stamp = f"{self.DAY}T{hour:02d}:{minute:02d}:00+05:30"
                events.append({
                    "event": "PAPER_TRADE_CLOSED",
                    "session": f"SYNTHETIC_{index:03d}",
                    "timestamp": stamp,
                    "buy_time": stamp,
                    "symbol": f"NFO:SYNTHETIC_OPTION_{index:03d}",
                    "buy_price": 100.0,
                    "sell_price": 110.0,
                    "quantity": 1,
                    "gross_pnl": 11.0,
                    "fees": {"total": 1.0},
                    "net_pnl": 10.0,
                })
            path = Path(folder) / f"{self.DAY}_NIFTY_AUDIT_SYNTHETIC.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            with patch.object(publisher, "JOURNALS", Path(folder)):
                return publisher.snapshot("NIFTY", "ARCHIVED_SESSION", "AUDIT_ONLY", day=self.DAY)

    def test_display_ledger_is_capped_but_full_day_totals_are_not(self):
        result = self.snapshot_with_synthetic_closed_trades(31)
        self.assertEqual(result["closed_trades"], 31)
        self.assertEqual(result["net_pnl"], 310.0)
        self.assertEqual(result["pnl_coverage"], 31)
        self.assertEqual(len(result["trade_ledger"]), 30)

    @unittest.expectedFailure
    def test_known_defect_strategy_totals_should_match_all_31_trades(self):
        result = self.snapshot_with_synthetic_closed_trades(31)
        counts = sum(row["closed_trades"] for row in result["strategy_stats"].values())
        pnl = sum(row["net_pnl"] for row in result["strategy_stats"].values())
        self.assertEqual(counts, result["closed_trades"])
        self.assertAlmostEqual(pnl, result["net_pnl"])


if __name__ == "__main__":
    unittest.main()
