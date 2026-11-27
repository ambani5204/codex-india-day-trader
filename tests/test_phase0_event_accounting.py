"""Synthetic regressions only; no private journal or Firestore access."""
import unittest
from deploy.phase0_event_accounting import audit_event_accounting as audit

S = [{"session_id": "s", "run_id": "r"}]
SIG = {"kind": "SIGNAL", "event_id": "e1", "session_id": "s", "run_id": "r"}
TRADE = {"kind": "CLOSED_TRADE", "event_id": "e2", "trade_id": "t1", "session_id": "s", "run_id": "r", "gross_pnl": "110.25", "total_costs": "10.25", "net_pnl": "100.00"}

class EventAccountingTests(unittest.TestCase):
    def test_match(self):
        self.assertTrue(audit(S, [SIG, TRADE], [TRADE, SIG])["ok"])
    def test_missing_manifest(self):
        self.assertEqual(audit(None, [], [])["reason"], "MISSING_SESSION_MANIFEST")
    def test_orphan(self):
        self.assertEqual(audit(S, [dict(SIG, run_id="other")], [])["reason"], "JOURNAL_ORPHAN_EVENT")
    def test_duplicate_event(self):
        self.assertEqual(audit(S, [SIG, SIG], [SIG])["reason"], "JOURNAL_DUPLICATE_EVENT")
    def test_duplicate_trade(self):
        self.assertEqual(audit(S, [TRADE, dict(TRADE, event_id="e3")], [])["reason"], "JOURNAL_DUPLICATE_TRADE")
    def test_missing_cost(self):
        x = dict(TRADE); del x["total_costs"]
        self.assertEqual(audit(S, [x], [])["reason"], "JOURNAL_MISSING_PNL_COVERAGE")
    def test_bad_net(self):
        self.assertEqual(audit(S, [dict(TRADE, net_pnl="110.25")], [])["reason"], "JOURNAL_AFTER_COST_MISMATCH")
    def test_identity_mismatch_equal_counts(self):
        self.assertEqual(audit(S, [SIG], [dict(SIG, event_id="different")])["reason"], "EVENT_OR_ACCOUNTING_MISMATCH")
    def test_cost_mismatch(self):
        x = dict(TRADE, gross_pnl="111.25", net_pnl="101.00")
        self.assertEqual(audit(S, [TRADE], [x])["reason"], "EVENT_OR_ACCOUNTING_MISMATCH")
    def test_nonfinite(self):
        self.assertEqual(audit(S, [dict(TRADE, gross_pnl="NaN")], [])["reason"], "JOURNAL_INVALID_PNL")
    def test_private_output(self):
        self.assertNotIn("t1", str(audit(S, [TRADE], [SIG])))
if __name__ == "__main__":
    unittest.main()
