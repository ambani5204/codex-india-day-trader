"""Phase 11 S11.1: frozen realistic target bands and classifier."""
import unittest

from india_trader import performance_targets as pt


class Bands(unittest.TestCase):
    def test_bands_are_frozen(self):
        with self.assertRaises(Exception):
            pt.BANDS_15K["day"].expected = 9999.0

    def test_unrealistic_10pct_recorded_as_rejected(self):
        self.assertEqual(pt.UNREALISTIC_DAILY_TARGET_REJECTED_AT_RS, 1500)
        self.assertIn("beyond global market capacity",
                      pt.UNREALISTIC_DAILY_TARGET_REJECTED_REASON)


class Classify(unittest.TestCase):
    def test_hard_stop_takes_precedence(self):
        r = pt.classify_day(-600.0, trades=5)
        self.assertEqual(r["verdict"], pt.STOP_HIT)

    def test_green_day(self):
        r = pt.classify_day(300.0, trades=5)
        self.assertEqual(r["verdict"], pt.GREEN)
        self.assertEqual(r["cadence"], "ON_TARGET")

    def test_flat_day(self):
        self.assertEqual(pt.classify_day(-50.0, trades=3)["verdict"], pt.FLAT)

    def test_red_day(self):
        self.assertEqual(pt.classify_day(-450.0, trades=4)["verdict"], pt.RED)

    def test_cadence_under_over(self):
        self.assertEqual(pt.classify_day(0, trades=1)["cadence"], "UNDER")
        self.assertEqual(pt.classify_day(0, trades=9)["cadence"], "OVER")
        self.assertEqual(pt.classify_day(0, trades=0)["cadence"], "NONE")

    def test_no_data(self):
        self.assertEqual(pt.classify_day(None)["verdict"], pt.NO_DATA)


class Rollups(unittest.TestCase):
    def test_week_sums_and_classifies(self):
        r = pt.classify_week([200, -100, 300, -50, 100])
        self.assertAlmostEqual(r["net_pnl"], 450.0)
        self.assertIn(r["verdict"], (pt.GREEN, pt.FLAT))

    def test_week_stop_hit(self):
        self.assertEqual(pt.classify_week([-500, -500, -500, -500, -200])["verdict"],
                         pt.STOP_HIT)

    def test_month_green_requires_expected(self):
        r = pt.classify_month([75.0] * 22)  # exactly average
        self.assertEqual(r["verdict"], pt.GREEN)

    def test_month_ignores_missing(self):
        r = pt.classify_month([100, None, 100, None, 100])
        self.assertAlmostEqual(r["net_pnl"], 300.0)


if __name__ == "__main__":
    unittest.main()
