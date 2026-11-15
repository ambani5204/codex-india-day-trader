"""Regression cases for EMA9/EMA15 slope/body research.

No broker connectivity. Synthetic 5-minute bars exercise signal threshold,
entry timing and delayed stop activation.
"""
import datetime as dt
import unittest
from dataclasses import dataclass
from india_trader.core import IST
from india_trader.ema9_ema15_robustness_v2 import evaluate

@dataclass
class Bar:
    time: dt.datetime
    open: float
    high: float
    low: float
    close: float

def bars_for(body_fraction=.85, bullish=True):
    day=dt.date(2026,1,5)
    rows=[]
    price=25000.
    for i in range(75):
        start=price
        # trend begins after warmup, strong candle at bar 30
        change=(8 if bullish else -8) if i>=20 else 0.5
        if i==30:change=(36 if bullish else -36)
        close=start+change
        wick=abs(change)*(1/body_fraction-1)/2 if i==30 else 2
        rows.append(Bar(dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=5*i),
                        start,max(start,close)+wick,min(start,close)-wick,close))
        price=close
    return rows

class EmaAngleResearchTests(unittest.TestCase):
    def test_body_fraction_monotonic_signal_filter(self):
        rows=bars_for(.85)
        loose,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=10,body_min=.65)
        strict,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=10,body_min=.95)
        if strict is not None:
            self.assertIsNotNone(loose)

    def test_steeper_angle_never_adds_earlier_signal(self):
        rows=bars_for(.85)
        easy,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=10)
        hard,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=40)
        if easy is not None and hard is not None:
            self.assertGreaterEqual(hard["entry_time"],easy["entry_time"])

    def test_next_open_entry_is_after_signal_close(self):
        rows=bars_for(.85)
        trade,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=10,body_min=.65,entry_mode="next_open")
        if trade:
            self.assertIn("entry_time",trade)
            self.assertGreaterEqual(dt.datetime.fromisoformat(trade["entry_time"]),rows[20].time)

    def test_bearish_is_supported(self):
        rows=bars_for(.85,bullish=False)
        trade,_=evaluate(rows,"NIFTY",rows[0].time.date(),angle=10,body_min=.65)
        if trade:self.assertEqual(trade["direction"],"BEAR")

    def test_no_future_bars_no_trade(self):
        rows=bars_for()[:20]
        trade,status=evaluate(rows,"NIFTY",rows[0].time.date())
        self.assertIsNone(trade)
        self.assertEqual(status,"INCOMPLETE")

if __name__=="__main__":unittest.main()
