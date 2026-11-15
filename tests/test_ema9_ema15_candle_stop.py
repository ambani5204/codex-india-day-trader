import datetime as dt
import unittest
from types import SimpleNamespace
from india_trader.ema9_ema15_live_rules import Signal,levels,advance

def signal(side,stop):
    return Signal(side,"2026-01-05T10:00:00+05:30","2026-01-05T10:05:00+05:30",100.,stop,20.,.85)

class CandleStopTests(unittest.TestCase):
    def test_bullish_candle_low_defines_r(self):
        x=levels(signal(1,95.),101.)
        self.assertEqual((x["stop"],x["risk_points"],x["t1"],x["t2"],x["trail_stop"]),(95.,6.,113.,119.,107.))
    def test_bearish_candle_high_defines_r(self):
        x=levels(signal(-1,105.),99.)
        self.assertEqual((x["stop"],x["risk_points"],x["t1"],x["t2"],x["trail_stop"]),(105.,6.,87.,81.,93.))
    def test_invalid_entry_rejected(self):
        with self.assertRaises(ValueError):levels(signal(1,95.),94.)
    def test_t1_does_not_instantly_activate_trailing_stop(self):
        state={"side":1,**levels(signal(1,95.),101.),"t1_hit":False}
        bar=SimpleNamespace(open=102.,low=99.,high=120.)
        event,next_state=advance(state,bar)
        self.assertEqual(event,"T1_REACHED")
        self.assertTrue(next_state["t1_hit"])
        event,_=advance(next_state,SimpleNamespace(open=108.,low=106.,high=110.))
        self.assertEqual(event,"STOP")
    def test_stop_first_when_stop_and_target_same_bar(self):
        state={"side":1,**levels(signal(1,95.),101.),"t1_hit":False}
        event,_=advance(state,SimpleNamespace(open=102.,low=94.,high=120.))
        self.assertEqual(event,"STOP")
if __name__=="__main__":unittest.main()
