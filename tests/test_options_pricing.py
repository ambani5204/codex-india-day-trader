"""Black-Scholes pricer vs known values + parity/greek properties."""
import math
import unittest

from india_trader import options_pricing as op


class BlackScholes(unittest.TestCase):
    def test_atm_call_known_value(self):
        # spot=strike=100, t=1, r=0, sigma=0.2 -> C=7.9656, delta=0.53983
        self.assertAlmostEqual(op.price(100, 100, 1.0, 0.0, 0.2, call=True), 7.9656, places=3)
        self.assertAlmostEqual(op.delta(100, 100, 1.0, 0.0, 0.2, call=True), 0.53983, places=4)

    def test_put_call_parity(self):
        c = op.price(100, 95, 0.5, 0.06, 0.25, call=True)
        p = op.price(100, 95, 0.5, 0.06, 0.25, call=False)
        self.assertAlmostEqual(c - p, 100 - 95 * math.exp(-0.06 * 0.5), places=6)

    def test_theta_negative_and_decay_positive(self):
        self.assertLess(op.theta_per_day(100, 100, 0.05, 0.0, 0.2, call=True), 0)
        d = op.decay_over_minutes(25800, 25800, 0.0, 0.15, minutes_held=60, days_to_expiry=2, call=True)
        self.assertGreater(d, 0)

    def test_intrinsic_at_expiry(self):
        self.assertAlmostEqual(op.price(110, 100, 0.0, 0.05, 0.2, call=True), 10.0, places=9)
        self.assertAlmostEqual(op.price(90, 100, 0.0, 0.05, 0.2, call=True), 0.0, places=9)

    def test_delta_bounds(self):
        self.assertGreater(op.delta(26000, 25800, 0.01, 0.06, 0.15, True), 0.5)  # ITM call
        self.assertLess(op.delta(25600, 25800, 0.01, 0.06, 0.15, True), 0.5)     # OTM call


if __name__ == "__main__":
    unittest.main()
