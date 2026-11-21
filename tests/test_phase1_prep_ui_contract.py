"""Synthetic-only tests for the proposed, unintegrated Phase 1 UI contract."""
import unittest

from deploy.phase1_prep_ui_contract import classify_paper_kpi, workflow_display_state


def row(**overrides):
    result = {"data_type": "PAPER_SIMULATION", "market": "NIFTY",
              "closed_trades": 1, "pnl_coverage": 1, "net_pnl": -12.5}
    result.update(overrides)
    return result


class Phase1PreparationContractTests(unittest.TestCase):
    def test_verified_paper_kpi(self):
        self.assertEqual(classify_paper_kpi(row()),
                         {"status": "VERIFIED_PAPER", "net_pnl": -12.5})

    def test_partial_coverage_never_shows_pnl(self):
        result = classify_paper_kpi(row(closed_trades=2, pnl_coverage=1))
        self.assertIsNone(result["net_pnl"])

    def test_proxy_never_shows_options_pnl(self):
        self.assertEqual(classify_paper_kpi(row(data_type="PROXY_RESEARCH"))["status"],
                         "PROXY_RESEARCH")

    def test_duplicate_session_blocks_pnl(self):
        self.assertEqual(classify_paper_kpi(row(), duplicate_sessions=True)["net_pnl"], None)

    def test_missing_and_malformed_values(self):
        for candidate in (None, {}, row(pnl_coverage=True), row(net_pnl=float("nan")),
                          row(net_pnl=float("inf")), row(net_pnl=None)):
            self.assertIsNone(classify_paper_kpi(candidate)["net_pnl"])

    def test_zero_trades_is_not_zero_pnl(self):
        result = classify_paper_kpi(row(closed_trades=0, pnl_coverage=0, net_pnl=None))
        self.assertEqual(result["status"], "VERIFIED_NO_CLOSED_TRADES")
        self.assertIsNone(result["net_pnl"])

    def test_workflow_states_distinct(self):
        for state in ("FAILED", "CANCELLED", "COMPLETED", "RUNNING"):
            self.assertEqual(workflow_display_state(state), state)
        self.assertEqual(workflow_display_state("RUNNING", stale=True), "STALE")
        self.assertEqual(workflow_display_state("unexpected"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
