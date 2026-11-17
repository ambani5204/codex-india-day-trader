"""Regression guard: no arbitrary percentage option stops in live paper strategies."""
import inspect
import unittest
from india_trader import ema9_v2_live_sidecar, three_candle_live_sidecar

class StrategyStopPolicyTests(unittest.TestCase):
    def test_fibonacci_option_exits_follow_index_structure(self):
        source=inspect.getsource(ema9_v2_live_sidecar.run_market)
        self.assertNotIn('option_stop=',source)
        self.assertNotIn('option_target=',source)
        self.assertIn('index_stop or index_target or eod',source)
    def test_three_candle_option_exits_follow_index_structure(self):
        source=inspect.getsource(three_candle_live_sidecar.run)
        self.assertNotIn('premium_stop=',source)
        self.assertNotIn('premium_target=',source)
        self.assertIn('if stop or target or eod:',source)
if __name__=="__main__":
    unittest.main()
