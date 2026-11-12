"""No-credentials tests for experimental all-session Indian paper strategy."""
import datetime as dt
import unittest
from india_trader.core import Bar, IST
from india_trader.intraday_lab import intraday_signal, select_credit_spread, spread_mark
from india_trader.upstox import UpstoxError


def candle(minute,close,high=None,low=None):
    t=dt.datetime(2026,11,12,9,minute,tzinfo=IST)
    high=high if high is not None else close+1
    low=low if low is not None else close-1
    return Bar(t,close,high,low,close)


def opt(typ,key,delta,bid,ask):
    return {'instrument_key':key,'option_greeks':{'delta':delta,'iv':24.0},
            'market_data':{'bid_price':bid,'ask_price':ask,'bid_qty':1000,'ask_qty':1000}}


def chain_and_master():
    expiry='2026-11-12'
    records=[];chain=[]
    for strike,delta,bid,ask in ((90,-.25,7,7.5),(85,-.08,3,3.5),(80,-.03,1,1.5)):
        key=f'BSE_FO|{strike}P'
        records.append({'segment':'BSE_FO','instrument_type':'PE',
                        'underlying_symbol':'SENSEX','instrument_key':key,
                        'expiry':expiry,'strike_price':strike,'lot_size':20})
        chain.append({'expiry':expiry,'strike_price':strike,
                      'put_options':opt('PE',key,delta,bid,ask)})
    return chain,records


class IntradaySignalTests(unittest.TestCase):
    def test_orb_trigger_requires_closed_five_minute_bar(self):
        bars=[candle(15,100,101,99),candle(20,100,101,99),
              candle(25,100,101,99),candle(30,102,103,101)]
        signal=intraday_signal(bars,dt.datetime(2026,11,12,9,35,2,tzinfo=IST))
        self.assertEqual(signal['direction'],'BULL')
        self.assertEqual(signal['strategy'],'OPENING_RANGE_BREAKOUT')
        self.assertIsNone(intraday_signal(bars,dt.datetime(2026,11,12,9,34,59,tzinfo=IST)))
        self.assertIsNone(intraday_signal(bars,dt.datetime(2026,11,12,9,37,2,tzinfo=IST)))

    def test_no_repeat_same_candle(self):
        bars=[candle(15,100),candle(20,100),candle(25,100),
              candle(30,102,104,101)]
        now=dt.datetime(2026,11,12,9,35,5,tzinfo=IST)
        self.assertIsNone(intraday_signal(bars,now,bars[-1].time))

    def test_bearish_opening_break(self):
        bars=[candle(15,100,101,99),candle(20,100,101,99),
              candle(25,100,101,99),candle(30,98,99,97)]
        signal=intraday_signal(bars,dt.datetime(2026,11,12,9,35,2,tzinfo=IST))
        self.assertEqual(signal['direction'],'BEAR')


class SpreadRiskTests(unittest.TestCase):
    def setUp(self):
        self.chain,self.master=chain_and_master()
        self.day=dt.date(2026,11,12)
        self.settings={'capital_inr':100000,'max_loss_per_trade_inr':500,
                       'max_allocation_fraction':.25,'paper':True,'allow_live_orders':False}

    def test_put_credit_spread_has_hedge_and_capped_worst_case(self):
        p=select_credit_spread(self.master,self.chain,'SENSEX','BULL',100,
                               self.day,self.settings,expiry='2026-11-12')
        self.assertEqual(p['option_type'],'PE')
        self.assertGreater(p['short_strike'],p['long_strike'])
        self.assertNotEqual(p['short_key'],p['long_key'])
        self.assertLessEqual(p['estimated_max_expiry_loss_after_fees'],500)
        self.assertTrue(p['margin_not_verified'])
        self.assertEqual(p['quantity'],20)

    def test_tight_risk_budget_rejects_spread(self):
        cfg={**self.settings,'max_loss_per_trade_inr':20}
        with self.assertRaises(UpstoxError):
            select_credit_spread(self.master,self.chain,'SENSEX','BULL',100,self.day,
                                 cfg,expiry='2026-11-12')

    def test_no_liquidity_refuses_entry_and_exit(self):
        p=select_credit_spread(self.master,self.chain,'SENSEX','BULL',100,
                               self.day,self.settings,expiry='2026-11-12')
        broken=[dict(self.chain[0],put_options=dict(self.chain[0]['put_options'],
             market_data={'bid_price':7,'ask_price':7.5,'bid_qty':0,'ask_qty':0})),
             *self.chain[1:]]
        with self.assertRaises(UpstoxError):
            spread_mark(p,broken,'SENSEX',dt.datetime(2026,11,12,14,45,tzinfo=IST))

    def test_expiry_exit_is_early_and_uses_two_leg_prices(self):
        p=select_credit_spread(self.master,self.chain,'SENSEX','BULL',100,
                               self.day,self.settings,expiry='2026-11-12')
        result=spread_mark(p,self.chain,'SENSEX',dt.datetime(2026,11,12,14,46,tzinfo=IST))
        self.assertEqual(result['reason'],'TIME_EXIT')
        self.assertIn('INDICATIVE',result['source'])
        self.assertGreater(result['fees'],0)


if __name__=='__main__':
    unittest.main()
