"""Offline daywise schedule and Upstox delta contract selection tests."""
import datetime as dt
import unittest
from unittest.mock import patch

from india_trader.schedule import market_for_day
from india_trader.upstox import UpstoxError, UpstoxReader, select_delta_contract


def records(expiry='2026-11-17'):
    return [
        {'segment': 'NSE_FO', 'instrument_type': 'CE', 'underlying_symbol': 'NIFTY',
         'instrument_key': 'NSE_FO|CE1', 'expiry': expiry, 'strike_price': 26000,
         'lot_size': 65, 'trading_symbol': 'NIFTY26000CE'},
        {'segment': 'NSE_FO', 'instrument_type': 'CE', 'underlying_symbol': 'NIFTY',
         'instrument_key': 'NSE_FO|CE2', 'expiry': expiry, 'strike_price': 26050,
         'lot_size': 65, 'trading_symbol': 'NIFTY26050CE'},
    ]


def call(key, strike, delta, ask=30.0, bid=29.8, quantity=1000):
    return {'expiry': '2026-11-17', 'strike_price': strike,
            'call_options': {'instrument_key': key,
                             'option_greeks': {'delta': delta, 'iv': 13.0, 'theta': -2.0},
                             'market_data': {'ask_price': ask, 'bid_price': bid,
                                             'ask_qty': quantity, 'bid_qty': quantity}}}


class DaywiseAndDeltaTests(unittest.TestCase):
    def setUp(self):
        self.day = dt.date(2026, 11, 16)
        self.risk = {'capital_inr': 100000, 'max_loss_per_trade_inr': 500,
                     'max_allocation_fraction': 0.25}

    def test_schedule_all_week(self):
        expected = ['NIFTY', 'NIFTY', 'SENSEX', 'SENSEX', 'NIFTY', None, None]
        self.assertEqual([market_for_day(self.day + dt.timedelta(days=i))
                          for i in range(7)], expected)

    def test_delta_takes_priority_over_nearest_strike(self):
        chain = [call('NSE_FO|CE1', 26000, 0.41),
                 call('NSE_FO|CE2', 26050, 0.50)]
        r = select_delta_contract(records(), chain, 'NIFTY', 'BUY', 26001,
                                  self.day, self.risk)
        self.assertEqual(r['instrument_key'], 'NSE_FO|CE2')
        self.assertEqual(r['delta'], 0.50)
        self.assertEqual(r['expiry'], '2026-11-17')
        self.assertFalse(r['expiry_day_trade'])
        self.assertLess(r['estimated_stop_loss_including_charges'], 500)

    def test_premium_cap_and_risk_filter_block_expensive_options(self):
        with self.assertRaisesRegex(UpstoxError, 'No contract passed'):
            select_delta_contract(records(), [call('NSE_FO|CE1', 26000, 0.5, ask=400, bid=399)],
                                  'NIFTY', 'BUY', 26000, self.day, self.risk)

    def test_rejects_missing_delta_or_depth(self):
        with self.assertRaisesRegex(UpstoxError, 'No contract passed'):
            select_delta_contract(records(), [call('NSE_FO|CE1', 26000, 0.5, quantity=10)],
                                  'NIFTY', 'BUY', 26000, self.day, self.risk)
        with self.assertRaisesRegex(UpstoxError, 'No contract passed'):
            select_delta_contract(records(), [call('NSE_FO|CE1', 26000, -0.5)],
                                  'NIFTY', 'BUY', 26000, self.day, self.risk)

    def test_expiry_day_itself_is_blocked(self):
        with self.assertRaises(UpstoxError):
            select_delta_contract(records(), [call('NSE_FO|CE1', 26000, 0.5)],
                                  'NIFTY', 'BUY', 26000, dt.date(2026, 11, 17), self.risk)

    def test_api_chain_path(self):
        api = UpstoxReader(token='MOCK_ONLY')
        with patch.object(api, 'get', return_value=[call('NSE_FO|CE1', 26000, 0.5)]) as get:
            result = api.option_chain('NSE_INDEX|Nifty 50', '2026-11-17')
        self.assertEqual(len(result), 1)
        self.assertEqual(get.call_args.args[0], '/v2/option/chain')

    def test_bad_delta_bounds_are_blocked(self):
        with self.assertRaises(UpstoxError):
            select_delta_contract(records(), [call('NSE_FO|CE1', 26000, 0.5)],
                                  'NIFTY', 'BUY', 26000, self.day, self.risk,
                                  delta_min=.7, delta_max=.8, target_delta=.5)


if __name__ == '__main__':
    unittest.main()
