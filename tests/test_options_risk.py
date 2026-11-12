"""Offline scenario matrix for India advanced options position / stop risk rules.

No network, no trading account, no real orders. Fixtures are synthetic.
"""
import datetime as dt
import unittest

from india_trader.core import Bar, IST
from india_trader.paper_sim import PaperEngine,Quote
from india_trader.options_risk import (atr_5m,index_stop_plan,
                                       size_long_option,select_long_risk_managed)
from india_trader.intraday_lab import select_credit_spread,spread_mark
from india_trader.upstox import UpstoxError


TODAY=dt.date(2026,11,12)
NOW=dt.datetime(2026,11,12,9,35,2,tzinfo=IST)
CFG={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
     'capital_inr':100000,'max_loss_per_trade_inr':500,
     'max_daily_loss_inr':1500,'max_allocation_fraction':.25}


def opening_candles():
    t=lambda minute:dt.datetime(2026,11,12,9,minute,tzinfo=IST)
    return [Bar(t(15),1000,1005,995,1000),
            Bar(t(20),1000,1005,995,1000),
            Bar(t(25),1000,1005,995,1000),
            Bar(t(30),1020,1025,1015,1020)]


def plan(index_gap=2):
    return {'index_risk_points':index_gap,'index_stop':1000-index_gap,
            'index_spot':1000,'basis':'EXAMPLE',
            'atr_5m':None}


def credit_fixture():
    chain=[];master=[]
    for strike,delta,bid,ask in ((900,-.25,24.05,24.29),
                                 (870,-.08,5,5.05),
                                 (860,-.03,1,1.01)):
        key=f'BSE_FO|{strike}P'
        chain.append({'expiry':TODAY.isoformat(),'strike_price':strike,
                      'put_options':{'instrument_key':key,
                          'option_greeks':{'delta':delta,'iv':24},
                          'market_data':{'bid_price':bid,'ask_price':ask,
                                         'bid_qty':1000,'ask_qty':1000}}})
        master.append({'segment':'BSE_FO','instrument_type':'PE',
                       'underlying_symbol':'SENSEX','instrument_key':key,
                       'expiry':TODAY.isoformat(),'strike_price':strike,
                       'lot_size':20})
    return master,chain


class IndexStopTests(unittest.TestCase):
    def test_orb_uses_midpoint_without_inventing_early_atr(self):
        signal={'strategy':'OPENING_RANGE_BREAKOUT','direction':'BULL'}
        p=index_stop_plan(opening_candles(),signal,1020,NOW)
        self.assertEqual(p['basis'],'OR_15_MIN_MIDPOINT')
        self.assertEqual(p['index_stop'],1000)
        self.assertEqual(p['index_risk_points'],20)
        self.assertIsNone(p['atr_5m'])

    def test_missing_index_candle_blocks_stop_plan(self):
        with self.assertRaises(UpstoxError):
            index_stop_plan(opening_candles()[:2]+opening_candles()[3:],
                            {'strategy':'OPENING_RANGE_BREAKOUT','direction':'BULL'},1020,NOW)

    def test_atr_uses_closed_bars_and_needs_minimum_history(self):
        origin=dt.datetime(2026,11,12,9,15,tzinfo=IST)
        bars=[Bar(origin+dt.timedelta(minutes=5*i),1000,1003,997,1000)
              for i in range(20)]
        self.assertAlmostEqual(atr_5m(bars),6)
        late=dt.datetime(2026,11,12,10,55,1,tzinfo=IST)
        p=index_stop_plan(bars,{'strategy':'EMA_8_21_CROSS','direction':'BEAR'},
                          1000,late)
        self.assertEqual(p['index_stop'],1009)
        self.assertEqual(p['basis'],'ATR_5M_14_X_1.5')
        with self.assertRaises(UpstoxError):
            atr_5m(bars[:14])


class LongOptionRiskTests(unittest.TestCase):
    def test_one_or_more_whole_lots_fit_500_rupees(self):
        p=size_long_option(100,99,.5,20,'BFO',CFG,plan(2))
        self.assertEqual(p['quantity']%20,0)
        self.assertLessEqual(p['quantity'],60)
        self.assertLessEqual(p['estimated_stop_loss_including_charges'],500)
        self.assertGreaterEqual(p['net_reward_risk'],1.5)

    def test_nifty_large_atr_stop_blocks_one_lot(self):
        with self.assertRaises(UpstoxError):
            size_long_option(100,99,.5,65,'NFO',CFG,plan(20))

    def test_fees_can_make_tiny_premium_target_inadequate(self):
        with self.assertRaises(UpstoxError) as ctx:
            size_long_option(10,9.9,.5,20,'BFO',CFG,plan(2))
        self.assertIn('reward:risk',str(ctx.exception))

    def test_remaining_daily_loss_is_binding(self):
        with self.assertRaises(UpstoxError):
            size_long_option(100,99,.5,20,'BFO',CFG,plan(2),remaining_daily_loss=25)

    def test_current_master_and_lot_depth_required_for_selector(self):
        expiry='2026-11-13'
        key='BSE_FO|CALL_1000'
        master=[{'segment':'BSE_FO','instrument_type':'CE',
                 'underlying_symbol':'SENSEX','instrument_key':key,
                 'expiry':expiry,'strike_price':1000,'lot_size':20}]
        chain=[{'expiry':expiry,'strike_price':1000,
                'call_options':{'instrument_key':key,
                  'option_greeks':{'delta':.5,'iv':13},
                  'market_data':{'ask_price':100,'bid_price':99,
                                 'ask_qty':1000,'bid_qty':1000}}}]
        p=select_long_risk_managed(master,chain,'SENSEX','BULL',1000,
                                   TODAY,CFG,plan(2),expiry)
        self.assertEqual(p['symbol'],'BFO:SENSEX_1000_2026-11-13_CE')
        self.assertGreater(p['risk_plan']['quantity'],0)
        self.assertLessEqual(p['risk_plan']['estimated_stop_loss_including_charges'],500)
        chain[0]['call_options']['market_data']['ask_qty']=20
        chain[0]['call_options']['market_data']['bid_qty']=20
        smaller=select_long_risk_managed(master,chain,'SENSEX','BULL',1000,
                                         TODAY,CFG,plan(2),expiry)
        self.assertEqual(smaller['risk_plan']['quantity'],20)
        chain[0]['call_options']['market_data']['ask_qty']=0
        with self.assertRaises(UpstoxError):
            select_long_risk_managed(master,chain,'SENSEX','BULL',1000,
                                     TODAY,CFG,plan(2),expiry)

    def test_entry_fill_gap_cannot_keep_invalid_500_rupee_trade(self):
        t=dt.datetime(2026,11,12,10,0,tzinfo=IST)
        e=PaperEngine('BFO:SENSEX_1000_2026-11-13_CE',20,100000,500,
                      fee_profile='UPSTOX',planned_stop=95,planned_target=130,
                      min_net_reward_risk=1.5,remaining_daily_loss=500)
        self.assertEqual(e.process(Quote(t,99,100,1000,1000),signal=True,now=t)['event'],'ENTRY_SIGNAL')
        fill=e.process(Quote(t+dt.timedelta(seconds=1),119,120,1000,1000),now=t+dt.timedelta(seconds=1))
        self.assertEqual(fill['event'],'ENTRY_REJECTED')
        self.assertEqual(fill['reason'],'CAPITAL_OR_MAX_LOSS_LIMIT')
        self.assertIsNone(e.position)

    def test_index_invalidation_issues_exit_not_fake_fill(self):
        t=dt.datetime(2026,11,12,10,0,tzinfo=IST)
        e=PaperEngine('BFO:SENSEX_1000_2026-11-13_CE',20,100000,500,
                      fee_profile='UPSTOX',planned_stop=95,planned_target=130)
        e.process(Quote(t,99,100,1000,1000),signal=True,now=t)
        e.process(Quote(t+dt.timedelta(seconds=1),99,100,1000,1000),now=t+dt.timedelta(seconds=1))
        self.assertIsNotNone(e.position)
        signal=e.process(Quote(t+dt.timedelta(seconds=2),98,99,1000,1000),
                         now=t+dt.timedelta(seconds=2),force_exit_reason='INDEX_STOP')
        self.assertEqual(signal['event'],'EXIT_SIGNAL')
        self.assertEqual(signal['reason'],'INDEX_STOP')
        self.assertIsNotNone(e.position)  # still requires a later executable quote


class ShortSpreadRiskTests(unittest.TestCase):
    def test_credit_spread_net_rr_and_expiry_worst_case_checked(self):
        master,chain=credit_fixture()
        p=select_credit_spread(master,chain,'SENSEX','BULL',1020,TODAY,
                               CFG,expiry=TODAY.isoformat(),
                               remaining_daily_loss=500,min_reward_risk=.25)
        self.assertLessEqual(p['estimated_max_expiry_loss_after_fees'],500)
        self.assertLessEqual(p['estimated_stop_net_loss'],500)
        self.assertGreaterEqual(p['net_reward_risk_at_credit_stop'],.25)
        self.assertGreater(p['estimated_target_net_profit'],0)
        self.assertGreater(p['short_strike'],p['long_strike'])

    def test_credit_risk_rejects_bad_reward_and_daily_cap(self):
        master,chain=credit_fixture()
        with self.assertRaises(UpstoxError):
            select_credit_spread(master,chain,'SENSEX','BULL',1020,TODAY,
                                 CFG,expiry=TODAY.isoformat(),min_reward_risk=.8)
        with self.assertRaises(UpstoxError):
            select_credit_spread(master,chain,'SENSEX','BULL',1020,TODAY,
                                 CFG,expiry=TODAY.isoformat(),
                                 remaining_daily_loss=100,min_reward_risk=.25)

    def test_credit_spread_exits_on_confirmed_index_invalidation(self):
        master,chain=credit_fixture()
        stop={'index_stop':1000,'basis':'OR_MIDPOINT'}
        p=select_credit_spread(master,chain,'SENSEX','BULL',1020,TODAY,CFG,
                               expiry=TODAY.isoformat(),min_reward_risk=.25,
                               index_stop_plan=stop)
        marked=spread_mark(p,chain,'SENSEX',
                           dt.datetime(2026,11,12,11,0,tzinfo=IST),index_close=990)
        self.assertEqual(marked['reason'],'INDEX_STOP')


if __name__=='__main__':
    unittest.main()
