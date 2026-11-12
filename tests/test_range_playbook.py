"""No-lookahead range-pattern and strategy/expiry mapping regression tests.

All prices and bars are SYNTHETIC; assertions never imply profitable trades.
"""
import datetime as dt
import unittest

from india_trader.core import Bar, IST
from india_trader.intraday_lab import intraday_signal
from india_trader.options_risk import index_stop_plan, size_long_option
from india_trader.advanced_forward import option_structure_priority
from india_trader.upstox import UpstoxError, select_atm


DAY=dt.date(2026,11,12)
def bar(minute,opened,high,low,close):
    return Bar(dt.datetime(2026,11,12,9,minute,tzinfo=IST),
               opened,high,low,close)
def opening():
    return [bar(15,100,101,99,100),
            bar(20,100,101,99,100),
            bar(25,100,101,99,100)]
def at(minute):
    return dt.datetime(2026,11,12,9,minute,tzinfo=IST)


class RangeEventTests(unittest.TestCase):
    def test_upside_breakout_is_bullish_but_only_after_close(self):
        candles=opening()+[bar(30,100.5,103,100,102)]
        self.assertIsNone(intraday_signal(candles,at(34)))
        signal=intraday_signal(candles,at(35))
        self.assertEqual(signal['range_pattern'],'BREAKOUT')
        self.assertEqual(signal['strategy'],'OPENING_RANGE_BREAKOUT')
        self.assertEqual(signal['direction'],'BULL')
        self.assertEqual(signal['confirmation'],'CLOSED_ABOVE_OR_HIGH')
        self.assertIsNone(intraday_signal(candles,at(36),candles[-1].time))

    def test_downside_breakout_is_bearish(self):
        signal=intraday_signal(opening()+[bar(30,99.5,100,97,98)],at(35))
        self.assertEqual(signal['direction'],'BEAR')
        self.assertEqual(signal['range_pattern'],'BREAKOUT')

    def test_upper_fakeout_is_bearish_no_outside_close(self):
        candles=opening()+[bar(30,100.8,103.0,99.5,100.6)]
        signal=intraday_signal(candles,at(35))
        self.assertEqual(signal['strategy'],'OPENING_RANGE_FAKEOUT')
        self.assertEqual(signal['direction'],'BEAR')
        self.assertEqual(signal['failed_breakout_side'],'UP')
        self.assertEqual(signal['sweep_extreme'],103)
        stop=index_stop_plan(candles,signal,100.6,at(35))
        self.assertEqual(stop['basis'],'OR_FAKEOUT_BEYOND_WICK_SWEEP')
        self.assertGreater(stop['index_stop'],103)
        self.assertEqual(stop['index_target'],100)

    def test_lower_fakeout_is_bullish_and_opposite_ce_side(self):
        candles=opening()+[bar(30,99.1,100.6,97,99.4)]
        signal=intraday_signal(candles,at(35))
        self.assertEqual(signal['strategy'],'OPENING_RANGE_FAKEOUT')
        self.assertEqual(signal['direction'],'BULL')
        stop=index_stop_plan(candles,signal,99.4,at(35))
        self.assertLess(stop['index_stop'],97)
        self.assertEqual(stop['index_target'],100)

    def test_upper_closed_breakout_then_reversal_is_bear_trap(self):
        candles=opening()+[bar(30,100,103,100,102),
                           bar(35,102,104,99.5,100.5)]
        self.assertEqual(intraday_signal(candles[:4],at(35))['range_pattern'],'BREAKOUT')
        signal=intraday_signal(candles,at(40))
        self.assertEqual(signal['strategy'],'OPENING_RANGE_TRAP')
        self.assertEqual(signal['direction'],'BEAR')
        self.assertEqual(signal['bars_outside'],1)
        self.assertEqual(signal['sweep_extreme'],104)
        stop=index_stop_plan(candles,signal,100.5,at(40))
        self.assertGreater(stop['index_stop'],104)
        self.assertEqual(stop['index_target'],99)
        self.assertEqual(stop['target_basis'],'OR_TRAP_OPPOSITE_RANGE_BOUNDARY')

    def test_lower_closed_breakout_then_reversal_is_bull_trap(self):
        candles=opening()+[bar(30,100,100,97,98),
                           bar(35,98,101,97,99.5)]
        signal=intraday_signal(candles,at(40))
        self.assertEqual(signal['strategy'],'OPENING_RANGE_TRAP')
        self.assertEqual(signal['direction'],'BULL')
        self.assertLess(signal['sweep_extreme'],99)
        stop=index_stop_plan(candles,signal,99.5,at(40))
        self.assertLess(stop['index_stop'],97)
        self.assertEqual(stop['index_target'],101)

    def test_four_outside_closes_do_not_mislabel_late_return_as_trap(self):
        candles=opening()+[bar(30,101,104,101,103),
                           bar(35,103,105,102,104),
                           bar(40,104,106,103,105),
                           bar(45,105,107,104,106),
                           bar(50,106,107,99.5,100.5)]
        self.assertIsNone(intraday_signal(candles,at(55)))

    def test_whipsaw_both_sides_in_one_candle_is_not_fakeout(self):
        candles=opening()+[bar(30,100,104,96,100)]
        self.assertIsNone(intraday_signal(candles,at(35)))

    def test_risk_reward_rejection_does_not_shift_stop_to_force_a_trade(self):
        candles=opening()+[bar(30,100.8,103,99.5,100.6)]
        signal=intraday_signal(candles,at(35))
        stop=index_stop_plan(candles,signal,100.6,at(35))
        settings={'capital_inr':100000,'max_loss_per_trade_inr':1000,
                  'max_allocation_fraction':.25}
        with self.assertRaises(UpstoxError):
            size_long_option(100,99,-.5,20,'BFO',settings,stop,min_rr=1.5)
        self.assertGreater(stop['index_stop'],103)  # Risk rule did NOT tighten.


class StructureAndExpiryTests(unittest.TestCase):
    def test_structure_preference_by_range_behavior_and_iv(self):
        for scenario,expect_high in [
            ('OPENING_RANGE_BREAKOUT',['LONG','CREDIT']),
            ('OPENING_RANGE_TRAP',['LONG','CREDIT']),
            ('OPENING_RANGE_FAKEOUT',['CREDIT','LONG']),
            ('EMA_8_21_CROSS',['LONG','CREDIT']),
            ('MEAN_REVERSION',['CREDIT','LONG'])]:
            with self.subTest(scenario=scenario):
                sig={'strategy':scenario,'direction':'BULL'}
                self.assertEqual(option_structure_priority(sig,24),expect_high)
                self.assertEqual(option_structure_priority(sig,12),['LONG'])
        with self.assertRaises(UpstoxError):
            option_structure_priority({'strategy':'UNKNOWN','direction':'BULL'},24)

    def test_non_expiry_bull_uses_ce_bear_uses_pe_and_current_expiry_is_skipped(self):
        records=[]
        for expiry in ('2026-11-12','2026-11-19','2026-11-26'):
            for opttype in ('CE','PE'):
                records.append({'segment':'BSE_FO','instrument_type':opttype,
                                'underlying_symbol':'SENSEX',
                                'instrument_key':f'BSE_FO|{opttype}_{expiry}',
                                'expiry':expiry,'strike_price':100,'lot_size':20})
        b=select_atm(records,'SENSEX','BUY',100,DAY)
        s=select_atm(records,'SENSEX','SELL',100,DAY)
        self.assertEqual((b['option_type'],b['expiry']),('CE','2026-11-19'))
        self.assertEqual((s['option_type'],s['expiry']),('PE','2026-11-19'))


if __name__=='__main__':
    unittest.main()
