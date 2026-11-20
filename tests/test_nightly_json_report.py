"""Regression tests for the real JSON report consumed by the nightly merger.

Fixtures are synthetic, offline and cannot be interpreted as trading evidence.
"""
import json
import tempfile
import unittest
from pathlib import Path

from deploy.merged_strategy_review import load_paper_report
from deploy.nightly_strategy_evaluation import write_paper_report


class NightlyPaperReportSerializationTests(unittest.TestCase):
    def test_serialized_paper_report_round_trips_through_real_merger(self):
        report = {
            "report_date": "2026-11-19",
            "status": "INSUFFICIENT_DATA",
            "verified_pnl_trades": 0,
            "net_pnl": None,
            "strategy_reviews": {},
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "paper_evaluation.json"
            write_paper_report(path, report)
            raw = path.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertFalse(raw.endswith(b"\\n"))
            self.assertEqual(json.loads(raw.decode("utf-8")), report)
            self.assertEqual(load_paper_report(path), report)

    def test_two_complete_reports_select_final_snapshot_without_adding_pnl(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper_evaluation.json"
            old = {"verified_pnl_trades": 1, "net_pnl": -10.0}
            latest = {"verified_pnl_trades": 2, "net_pnl": -2.0}
            write_paper_report(path, old)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(latest) + "\n")
            self.assertEqual(load_paper_report(path), latest)

    def test_invalid_literal_backslash_n_is_not_accepted_as_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper_evaluation.json"
            path.write_text('{"net_pnl": null}\\n', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_paper_report(path)


if __name__ == "__main__":
    unittest.main()
