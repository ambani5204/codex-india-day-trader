"""config/strategies.json loads, validates, defaults OFF, and only env-enables."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from india_trader import strategy_config as sc


class StrategyConfig(unittest.TestCase):
    def test_default_config_loads_and_all_disabled(self):
        cfg = sc.load()
        self.assertEqual(sc.enabled_strategies(cfg), [])  # nothing live until validated
        self.assertEqual(set(cfg["strategies"]),
                         {"S1_orb", "S2_supertrend_sma", "S3_utbot_macd", "S4_buffer_breakout",
                          "S5_sma_rsi", "S6_equity_rsima_scanner", "S7_reversal_v1"})
        self.assertTrue(cfg["common"]["options_buying_only"])

    def test_env_can_enable_but_not_change_params(self):
        os.environ["ALGOBANI_ENABLE_STRATEGIES"] = "S2_supertrend_sma, S4_buffer_breakout"
        try:
            cfg = sc.load()
            self.assertEqual(set(sc.enabled_strategies(cfg)), {"S2_supertrend_sma", "S4_buffer_breakout"})
            self.assertEqual(sc.strategy(cfg, "S2_supertrend_sma")["sma_n"], 20)  # unchanged
        finally:
            os.environ.pop("ALGOBANI_ENABLE_STRATEGIES", None)

    def test_env_unknown_strategy_fails_closed(self):
        os.environ["ALGOBANI_ENABLE_STRATEGIES"] = "S99_bogus"
        try:
            with self.assertRaises(sc.StrategyConfigError):
                sc.load()
        finally:
            os.environ.pop("ALGOBANI_ENABLE_STRATEGIES", None)

    def test_invalid_risk_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text(json.dumps({"common": {"square_off_ist": "1505", "no_new_entries_after_ist": "1445"},
                                     "strategies": {"X": {"enabled": True, "risk": {"NIFTY": {"sl": -1, "tp": 50}}}}}))
            with self.assertRaises(sc.StrategyConfigError):
                sc.load(str(p))


if __name__ == "__main__":
    unittest.main()
