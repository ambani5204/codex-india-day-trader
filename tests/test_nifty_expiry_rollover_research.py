import datetime as dt
import unittest
from india_trader.core import Bar, IST
from india_trader.nifty_expiry_rollover_research import candidates, replay

def bar(day,h,m,o,c,lo=None,hi=None):
    return Bar(dt.datetime.combine(day,dt.time(h,m),IST),o,
               max(o,c) if hi is None else hi,
               min(o,c) if lo is None else lo,c)

class ExpiryRolloverTests(unittest.TestCase):
    def test_strong_green_after_three_red(self):
        d=dt.date(2026,11,12)
        bars=[bar(d,14,15,100,98),bar(d,14,20,98,96),
              bar(d,14,25,96,94),bar(d,14,30,94,101)]
        found=candidates(bars)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["direction"],1)
        self.assertEqual(found[0]["signal_time"][-14:-9],"14:35")
    def test_weak_candle_not_triggered(self):
        d=dt.date(2026,11,12)
        bars=[bar(d,14,15,100,98),bar(d,14,20,98,96),
              bar(d,14,25,96,94),bar(d,14,30,94,94.2)]
        self.assertFalse(candidates(bars))
    def test_missing_session_refuses_simulated_fills(self):
        d=dt.date(2026,11,12)
        self.assertEqual(replay([],d)["status"],"INCOMPLETE_CANDLES")

if __name__=="__main__":unittest.main()
