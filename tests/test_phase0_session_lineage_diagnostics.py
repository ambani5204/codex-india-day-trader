"""Synthetic tests only; no Firestore access or real user data."""
import unittest

from deploy.phase0_session_lineage_diagnostics import (
    classify_market_date_lineage, safe_summary,
)


def row(run_id, day="2026-11-19", market="NIFTY", **kw):
    return {"data_type": "PAPER_SIMULATION", "date_ist": day,
            "market": market, "run_id": run_id, **kw}


class SessionLineageDiagnosticsTests(unittest.TestCase):
    def test_single_session_does_not_imply_journal_reconciliation(self):
        result = classify_market_date_lineage([row("synthetic-a")])
        self.assertEqual(result["status"], "NO_MULTIROW_GROUPS")

    def test_singleton_missing_run_id_fails_closed(self):
        result = classify_market_date_lineage([row(None)])
        self.assertEqual(result["status"], "BLOCKED_MISSING_RUN_ID")
        self.assertEqual(result["ambiguous_groups"], 0)
        self.assertIn("BLOCKED_MISSING_RUN_ID", safe_summary(result))

    def test_singleton_whitespace_run_id_fails_closed(self):
        self.assertEqual(classify_market_date_lineage([row("  ")])["status"],
                         "BLOCKED_MISSING_RUN_ID")

    def test_invalid_calendar_dates_fail_closed(self):
        for invalid in ("2026-11-31", "2026-02-29", "2026-11-1",
                        "2026-11-19T09:15:00", "19-11-2026"):
            self.assertEqual(classify_market_date_lineage([row("a", day=invalid)])["status"],
                             "INVALID_HISTORY_KEY")

    def test_distinct_run_ids_still_block_until_event_provenance(self):
        result = classify_market_date_lineage([row("synthetic-a"), row("synthetic-b")])
        self.assertEqual(result["status"], "BLOCKED_LINEAGE_UNVERIFIED")
        self.assertEqual(result["different_run_groups"], 1)
        self.assertEqual(result["ambiguous_groups"], 1)

    def test_same_run_id_is_not_assumed_valid_restart(self):
        result = classify_market_date_lineage([row("synthetic-a"), row("synthetic-a")])
        self.assertEqual(result["same_run_groups"], 1)
        self.assertEqual(result["status"], "BLOCKED_LINEAGE_UNVERIFIED")

    def test_missing_run_id_stays_blocked(self):
        result = classify_market_date_lineage([row("synthetic-a"), row(None)])
        self.assertEqual(result["missing_run_groups"], 1)

    def test_different_market_or_date_is_not_duplicate_group(self):
        result = classify_market_date_lineage([
            row("synthetic-a"), row("synthetic-b", market="SENSEX"),
            row("synthetic-c", day="2026-11-20")])
        self.assertEqual(result["ambiguous_groups"], 0)

    def test_invalid_rows_fail_closed(self):
        self.assertEqual(classify_market_date_lineage([None])["status"], "INVALID_ROWS")
        self.assertEqual(classify_market_date_lineage([row("a", day="")])["status"],
                         "INVALID_HISTORY_KEY")

    def test_proxy_is_not_mixed_with_paper(self):
        result = classify_market_date_lineage([
            row("a"), row("b", data_type="PROXY_RESEARCH")])
        self.assertEqual(result["ambiguous_groups"], 0)

    def test_safe_summary_never_leaks_run_ids_or_financial_values(self):
        result = classify_market_date_lineage([
            row("SECRET-RUN-A", net_pnl=12345.67),
            row("SECRET-RUN-B", net_pnl=98765.43)])
        summary = safe_summary(result)
        self.assertIn("BLOCKED_LINEAGE_UNVERIFIED", summary)
        for secret in ("SECRET-RUN-A", "SECRET-RUN-B", "12345", "98765", "NIFTY"):
            self.assertNotIn(secret, summary)

    def test_summary_rejects_unexpected_status(self):
        self.assertEqual(safe_summary({"status": "SECRET"}), "PHASE0_LINEAGE=INVALID_SUMMARY")


if __name__ == "__main__":
    unittest.main()
