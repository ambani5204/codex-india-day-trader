import unittest
from deploy.phase0_orphan_calendar_preflight import assess_evaluation_lineage as assess


class OrphanCalendarPreflightTests(unittest.TestCase):
    def test_saturday_orphan_preserved_as_unexplained(self):
        result = assess("2026-11-14", {"sessions": 1}, [])
        self.assertEqual(result["status"], "BLOCKED_NO_ELIGIBLE_HISTORY")
        self.assertEqual(result["calendar_status"], "WEEKEND")
        self.assertEqual(result["provenance"], "UNDETERMINED")

    def test_untyped_and_proxy_not_eligible(self):
        rows = [{"date_ist": "2026-11-14", "market": "NIFTY"},
                {"date_ist": "2026-11-14", "market": "NIFTY",
                 "data_type": "PROXY_RESEARCH"}]
        self.assertEqual(assess("2026-11-14", {}, rows)["matched_sessions"], 0)

    def test_missing_session_identity_fail_closed(self):
        rows = [{"date_ist": "2026-11-16", "market": "NIFTY",
                 "data_type": "PAPER_SIMULATION"}]
        self.assertEqual(assess("2026-11-16", {}, rows)["status"],
                         "BLOCKED_SESSION_IDENTITY")

    def test_valid_identity_still_requires_event_reconciliation(self):
        rows = [{"date_ist": "2026-11-16", "market": "NIFTY",
                 "data_type": "PAPER_SIMULATION", "session_id": "synthetic"}]
        self.assertEqual(assess("2026-11-16", {}, rows)["status"],
                         "REQUIRES_EVENT_RECONCILIATION")

    def test_explicit_holiday_and_invalid_date(self):
        self.assertEqual(assess("2026-11-17", {}, [],
                                holidays={"2026-11-17"})["calendar_status"], "HOLIDAY")
        self.assertEqual(assess("not-a-date", {}, [])["status"], "BLOCKED_INVALID_DATE")


if __name__ == "__main__":
    unittest.main()
