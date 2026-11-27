"""CHG-20261123-A2-1711: fail-closed offline calendar authorization tests."""
import unittest

from deploy.nightly_strategy_evaluation import authorized_trading_dates, require_authorized_date


class NightlyCalendarAuthorizationTests(unittest.TestCase):
    def test_missing_authority_fails_closed(self):
        for raw in (None, "", "  "):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                authorized_trading_dates(raw)

    def test_invalid_and_duplicate_dates_rejected(self):
        for raw in ("2026-11-23,2026-11-23", "2026-11-23,", "2026-02-30",
                    "2026-11-23, 2026-11-24", "2026-11-23T00:00:00"):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                authorized_trading_dates(raw)

    def test_non_authorized_date_rejected(self):
        allowed = authorized_trading_dates("2026-11-13,2026-11-16")
        with self.assertRaises(RuntimeError):
            require_authorized_date("2026-11-14", allowed)

    def test_authorized_special_session_is_not_assumed_invalid(self):
        # Authoritative calendar may explicitly contain weekend special sessions.
        allowed = authorized_trading_dates("2026-11-14")
        self.assertIsNone(require_authorized_date("2026-11-14", allowed))


if __name__ == "__main__":
    unittest.main()
