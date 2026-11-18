"""Offline checks for dual-market paper budgeting (no broker credentials)."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from india_trader.cli import paper_settings_partitioned
from deploy.cloud_paper_session import summarize
from india_trader.upstox_forward import _daily_risk
from india_trader.upstox import UpstoxError


class DualMarketPaperTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            'paper': True, 'allow_live_orders': False,
            'capital_inr': 100000, 'max_loss_per_trade_inr': 500,
            'max_daily_loss_inr': 1500, 'max_trades_per_day': 3,
        }

    def test_separate_market_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import patch
            with patch("deploy.cloud_paper_session.JOURNALS", Path(tmp)):
                (Path(tmp) / "2026-11-18_NIFTY_091500.jsonl").write_text(
                    json.dumps({"event": "INDEX_SIGNAL", "strategy": "EMA_8_21_CROSS"}) + "\\n" +
                    json.dumps({"event": "SESSION_SUMMARY"}) + "\\n")
                (Path(tmp) / "2026-11-18_SENSEX_091500.jsonl").write_text(
                    json.dumps({"event": "SESSION_SUMMARY"}) + "\\n")
                nifty = summarize("2026-11-18", "NIFTY", 0, "READY")
                sensex = summarize("2026-11-18", "SENSEX", 0, "READY")
                self.assertEqual(nifty["event_counts"]["INDEX_SIGNAL"], 1)
                self.assertEqual(sensex["event_counts"], {})
                self.assertEqual(nifty["sessions"], 1)
                self.assertEqual(sensex["sessions"], 1)

    def test_split_capital_and_risk(self):
        actual = paper_settings_partitioned(self.cfg, 2)
        self.assertEqual(actual['capital_inr'], 50000)
        self.assertEqual(actual['max_loss_per_trade_inr'], 250)
        self.assertEqual(actual['max_daily_loss_inr'], 750)
        self.assertEqual(actual['max_trades_per_day'], 1)
        self.assertTrue(actual['paper'])
        self.assertFalse(actual['allow_live_orders'])
        self.assertEqual(self.cfg['capital_inr'], 100000)

    def test_single_market_keeps_budget(self):
        actual = paper_settings_partitioned(self.cfg, 1)
        self.assertEqual(actual['capital_inr'], 100000)
        self.assertEqual(actual['max_trades_per_day'], 3)

    def test_invalid_partitions_are_blocked(self):
        with self.assertRaises(ValueError):
            paper_settings_partitioned(self.cfg, 0)
        with self.assertRaises(ValueError):
            paper_settings_partitioned(self.cfg, 3)

    def test_per_market_journals_are_isolated(self):
        d = date(2026, 11, 11)
        cfg = paper_settings_partitioned(self.cfg, 2)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / (d.isoformat() + '_SENSEX_091515.jsonl')
            p.write_text(json.dumps({'event': 'PAPER_BUY_FILLED'}) + '\n')
            # An unresolved SENSEX paper position must not block NIFTY's
            # independently budgeted paper worker.
            _daily_risk(tmp, d, cfg, market='NIFTY')
            with self.assertRaises(UpstoxError):
                _daily_risk(tmp, d, cfg, market='SENSEX')


if __name__ == '__main__':
    unittest.main()
