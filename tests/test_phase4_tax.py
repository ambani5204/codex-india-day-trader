"""Phase 4: F&O business-income tax layer (slab-based), hand-checked."""
import unittest

from india_trader.tax import fno_tax, net_after_tax


class Tax(unittest.TestCase):
    def test_loss_is_untaxed(self):
        r = fno_tax(-5000, other_income=0)
        self.assertEqual(r.total_tax, 0.0)

    def test_ten_lakh_from_zero_other_income(self):
        # new regime: 0-4L @0, 4-8L @5% = 20000, 8-10L @10% = 20000 -> 40000 +4% cess
        r = fno_tax(1_000_000, other_income=0)
        self.assertAlmostEqual(r.tax_before_cess, 40_000, places=2)
        self.assertAlmostEqual(r.cess, 1_600, places=2)
        self.assertAlmostEqual(r.total_tax, 41_600, places=2)

    def test_marginal_over_other_income(self):
        # other 8L already uses the low slabs; +4L trading sits in the 10% band
        r = fno_tax(400_000, other_income=800_000)
        self.assertAlmostEqual(r.tax_before_cess, 40_000, places=2)  # 4L @10%
        self.assertAlmostEqual(r.total_tax, 41_600, places=2)
        self.assertAlmostEqual(r.effective_rate_on_trading, 0.104, places=4)

    def test_net_after_tax(self):
        self.assertAlmostEqual(net_after_tax(1_000_000, 0), 1_000_000 - 41_600, places=2)


if __name__ == "__main__":
    unittest.main()
