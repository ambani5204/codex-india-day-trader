"""Offline safety checks for three-candle option paper integration."""
import datetime as dt
import unittest
from india_trader.core import Bar,IST
from india_trader.three_candle_top_down_v2 import test_day
from india_trader.three_candle_live_sidecar import OUT

class ThreeCandleIntegrationTests(unittest.TestCase):
    def test_no_future_bars_are_fabricated(self):
        day=dt.date(2026,11,13)
        prior=[Bar(dt.datetime(2026,11,12,9,15,tzinfo=IST),100,101,99,100)]
        now=[Bar(dt.datetime.combine(day,dt.time(9,15),IST),100,101,99,100)]
        status,trade,stages=test_day(now,prior,"NIFTY",day,2.,live_prefix=True)
        self.assertEqual(status,"OK")
        self.assertIsNone(trade)
        self.assertEqual(dict(stages),{})
    def test_historical_requires_complete_candles(self):
        day=dt.date(2026,11,13)
        bars=[Bar(dt.datetime.combine(day,dt.time(9,15),IST),100,101,99,100)]
        status,trade,_=test_day(bars,bars,"NIFTY",day,2.)
        self.assertEqual(status,"INCOMPLETE")
        self.assertIsNone(trade)
    def test_live_journal_isolated(self):
        self.assertEqual(str(OUT),"trader/three_candle_live")
if __name__=="__main__":unittest.main()
