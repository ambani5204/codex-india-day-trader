"""Overnight phone schedule tests: any start time, no duplicate same-day sessions."""
import datetime as dt
import unittest
from india_trader.core import IST
from deploy.termux_runner import next_session


def at(year,month,day,hour,minute=0):
    return dt.datetime(year,month,day,hour,minute,tzinfo=IST)


class OvernightScheduleTests(unittest.TestCase):
    def test_wednesday_night_waits_thursday_sensex(self):
        next_start, market = next_session(at(2026,11,11,22))
        self.assertEqual((next_start,market),(at(2026,11,12,9,15),'SENSEX'))

    def test_morning_start_at_any_hour_before_open(self):
        next_start,market = next_session(at(2026,11,13,6,25))
        self.assertEqual(next_start,at(2026,11,13,9,15))
        self.assertEqual(market,'NIFTY')

    def test_market_hours_start_immediately_without_backfilling(self):
        now=at(2026,11,12,11,12)
        next_start,market=next_session(now)
        self.assertEqual(next_start,now)
        self.assertEqual(market,'SENSEX')

    def test_after_close_waits_next_market_day(self):
        next_start,market=next_session(at(2026,11,13,18))
        self.assertEqual((next_start,market),(at(2026,11,16,9,15),'NIFTY'))

    def test_weekend_waits_monday(self):
        next_start,market=next_session(at(2026,11,14,10))
        self.assertEqual((next_start,market),(at(2026,11,16,9,15),'NIFTY'))

    def test_attempted_day_never_restarts_same_day(self):
        d=dt.date(2026,11,12)
        next_start,market=next_session(at(2026,11,12,10),attempted_day=d)
        self.assertEqual((next_start,market),(at(2026,11,13,9,15),'NIFTY'))

    def test_exact_open_and_cutoff(self):
        st,market=next_session(at(2026,11,12,9,15))
        self.assertEqual(st,at(2026,11,12,9,15))
        self.assertEqual(market,'SENSEX')
        st,market=next_session(at(2026,11,12,15,10))
        self.assertEqual(st,at(2026,11,13,9,15))
        self.assertEqual(market,'NIFTY')


if __name__=='__main__':
    unittest.main()
