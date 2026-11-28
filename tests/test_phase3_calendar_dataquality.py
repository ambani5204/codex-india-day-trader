"""Phase 3: trading calendar + data-quality coverage."""
import datetime as dt
import unittest

from india_trader import data_quality as dq
from india_trader import trading_calendar as cal
from india_trader.core import Bar

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class Calendar(unittest.TestCase):
    def test_weekend_not_trading(self):
        self.assertFalse(cal.is_trading_day(dt.date(2026, 11, 28)))  # Saturday
        self.assertFalse(cal.is_trading_day(dt.date(2026, 11, 29)))  # Sunday

    def test_listed_holiday_not_trading(self):
        self.assertTrue(cal.is_holiday(dt.date(2026, 1, 26)))        # Republic Day
        self.assertFalse(cal.is_trading_day(dt.date(2026, 1, 26)))
        self.assertEqual(cal.holiday_name(dt.date(2026, 1, 26)), "Republic Day")

    def test_normal_weekday_trades(self):
        self.assertTrue(cal.is_trading_day(dt.date(2026, 11, 30)))   # Monday
        self.assertIsNotNone(cal.session_bounds(dt.date(2026, 11, 30)))

    def test_trading_days_excludes_weekend_and_holiday(self):
        days = cal.trading_days(dt.date(2026, 1, 24), dt.date(2026, 1, 27))
        self.assertNotIn(dt.date(2026, 1, 24), days)  # Sat
        self.assertNotIn(dt.date(2026, 1, 25), days)  # Sun
        self.assertNotIn(dt.date(2026, 1, 26), days)  # Republic Day
        self.assertIn(dt.date(2026, 1, 27), days)     # Tue


class DataQuality(unittest.TestCase):
    def _full_session(self, day):
        return [Bar(dt.datetime.combine(day, t, IST), 100, 101, 99, 100)
                for t in dq.expected_stamps(day)]

    def test_complete_session(self):
        day = dt.date(2026, 11, 30)
        c = dq.session_coverage(self._full_session(day), day)
        self.assertEqual(c["present_in_hours"], 75)
        self.assertEqual(c["coverage_pct"], 100.0)
        self.assertTrue(c["complete"])

    def test_missing_bars_detected(self):
        day = dt.date(2026, 11, 30)
        bars = self._full_session(day)[:-5]  # drop last 5 bars
        c = dq.session_coverage(bars, day)
        self.assertEqual(c["missing_bars"], 5)
        self.assertFalse(c["complete"])

    def test_duplicate_detected(self):
        day = dt.date(2026, 11, 30)
        bars = self._full_session(day)
        bars.append(bars[0])
        c = dq.session_coverage(bars, day)
        self.assertTrue(c["duplicates"])
        self.assertFalse(c["complete"])

    def test_report_aggregates(self):
        d1, d2 = dt.date(2026, 11, 30), dt.date(2026, 12, 1)
        bars = self._full_session(d1) + self._full_session(d2)[:-3]
        r = dq.coverage_report(bars)
        self.assertEqual(r["sessions"], 2)
        self.assertEqual(r["complete_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
