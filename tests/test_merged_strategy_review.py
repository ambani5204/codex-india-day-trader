import unittest
from deploy.merged_strategy_review import merge, markdown


class MergedStrategyReviewTests(unittest.TestCase):
    def test_separates_evidence_from_hypotheses(self):
        paper = {"report_date": "2026-11-14", "sessions": 1,
                 "verified_pnl_trades": 1, "net_pnl": -1140.12,
                 "strategy_reviews": {"NIFTY:MEAN_REVERSION": {
                     "verified_trades": 1, "win_rate": 0.0,
                     "stop_exceedances": 1}}}
        report = merge(paper, {"status": "DATA_UNAVAILABLE"})
        self.assertEqual(report["paper"]["net_pnl"], -1140.12)
        self.assertEqual(len(report["investigations"]), 2)
        self.assertEqual(report["investigations"][0]["evidence_level"],
                         "OBSERVED_PAPER_EXECUTION")
        self.assertEqual(report["investigations"][1]["evidence_level"],
                         "HYPOTHESIS_NOT_VALIDATED")
        self.assertEqual(report["forward_research"]["results"], [])
        self.assertIn("human approval", markdown(report))

    def test_proxy_not_presented_as_option_pnl(self):
        paper = {"strategy_reviews": {}}
        forward = {"kind": "FROZEN_PROSPECTIVE_INDEX_RESEARCH_HUMAN_REVIEW_ONLY",
                   "status": "EVALUATED", "results": [{
                       "playbook": "ORB", "forward": {
                           "trades": 31, "net_total_r": 2.0,
                           "net_profit_factor": 1.3},
                       "qualified_proxy_only_for_human_review": True}]}
        report = merge(paper, forward)
        self.assertEqual(report["forward_research"]["results"][0]["evidence_level"],
                         "INDEX_FUTURES_COST_PROXY_NOT_OPTION_EXECUTION")


if __name__ == "__main__":
    unittest.main()
