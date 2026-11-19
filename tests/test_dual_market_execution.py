import unittest
from datetime import datetime,timedelta,timezone
from deploy.dual_market_execution import OptionContract,option_roundtrip,equity_intraday_roundtrip,require_option_validation
from india_trader.paper_sim import Quote

class DualMarketExecutionTests(unittest.TestCase):
    def test_option_net_after_all_charges(self):
        t=datetime(2026,11,18,10,0,tzinfo=timezone.utc)
        contract=OptionContract("NIFTY_TEST_CE","NFO","2026-11-24",25000,"CE",65)
        entry=Quote(t,100,101,1000,1000)
        exit=Quote(t+timedelta(minutes=10),110,111,1000,1000)
        result=option_roundtrip(contract,entry,exit,1,slippage_bps=0)
        self.assertEqual(result["gross_inr"],585)
        self.assertGreater(result["charges"]["total"],0)
        self.assertLess(result["net_inr"],585)
        self.assertEqual(require_option_validation(result),result)
    def test_missing_depth_fails_closed(self):
        t=datetime(2026,11,18,10,0,tzinfo=timezone.utc)
        contract=OptionContract("NIFTY_TEST_CE","NFO","2026-11-24",25000,"CE",65)
        with self.assertRaises(ValueError):
            option_roundtrip(contract,Quote(t,100,101,10,10),Quote(t+timedelta(minutes=1),110,111,10,10))
    def test_equity_mode_cannot_be_promoted_to_options(self):
        result=equity_intraday_roundtrip(100,105,100)
        self.assertLess(result["net_inr"],result["gross_inr"])
        with self.assertRaises(ValueError):
            require_option_validation(result)
if __name__=="__main__":unittest.main()
