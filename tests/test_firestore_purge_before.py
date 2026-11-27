"""Offline tests for the owner-requested Firestore purge planner (CHG-20261127-1205)."""

import unittest

from deploy import firestore_purge_before as purge


def s(v):
    return {"stringValue": v}


class PlanTests(unittest.TestCase):
    def test_only_strictly_before_cutoff_and_undated_kept(self):
        docs = [
            ("paper_history", "p/paper_history/2026-11-13_NIFTY", {"date_ist": s("2026-11-13")}),
            ("paper_history", "p/paper_history/2026-11-27_NIFTY", {"date_ist": s("2026-11-27")}),
            ("paper_evaluations", "p/paper_evaluations/latest", {"report_date": s("2026-11-26")}),
            ("paper_dashboard", "p/paper_dashboard/NIFTY", {"date_ist": s("2026-11-27")}),
            ("three_candle_nightly", "p/three_candle_nightly/2026-11-20_SENSEX", {}),
            ("config", "p/config/settings", {"mode": s("paper")}),
        ]
        delete, counts = purge.plan(docs, "2026-11-27")
        self.assertEqual(delete, ["p/paper_history/2026-11-13_NIFTY", "p/paper_evaluations/latest",
                                  "p/three_candle_nightly/2026-11-20_SENSEX"])
        self.assertEqual(counts[("config", "UNDATED_KEPT")], 1)
        self.assertEqual(counts[("paper_dashboard", "KEPT 2026-11-27")], 1)

    def test_field_date_wins_over_id(self):
        self.assertEqual(purge.doc_date("x/2026-11-01_A", {"date_ist": s("2026-11-27")}), "2026-11-27")

    def test_future_or_invalid_cutoff_refused(self):
        with self.assertRaises(SystemExit):
            purge.validate_cutoff("2026-11-28", "2026-11-27")
        with self.assertRaises(SystemExit):
            purge.validate_cutoff("27-11-2026", "2026-11-27")
        self.assertEqual(purge.validate_cutoff("2026-11-27", "2026-11-27"), "2026-11-27")

    def test_apply_requires_exact_confirmation(self):
        today = purge.dt.datetime.now(purge.IST).date().isoformat()
        self.assertEqual(purge.main(["--cutoff", today, "--mode", "apply", "--confirm", "yes"]), 2)

    def test_dry_run_without_credentials_does_nothing(self):
        today = purge.dt.datetime.now(purge.IST).date().isoformat()
        self.assertEqual(purge.main(["--cutoff", today]), 2)


if __name__ == "__main__":
    unittest.main()
