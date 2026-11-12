"""Offline integration test for experimental all-day credit spreads with no real API calls."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from india_trader.core import Bar, IST
from india_trader.advanced_forward import run_advanced


class Clock:
    def __init__(self):
        self.now=dt.datetime(2026,11,12,9,35,2,tzinfo=IST)
    def clock(self):
        return self.now
    def sleep(self,secs):
        # Advance quickly through session; no real-time delays.
        self.now+=dt.timedelta(minutes=5)


class MockApi:
    def __init__(self,clock):
        self.clock=clock
    def candles(self,index):
        t=lambda minute:dt.datetime(2026,11,12,9,minute,tzinfo=IST)
        return [Bar(t(15),1000,1005,995,1000),Bar(t(20),1000,1005,995,1000),
                Bar(t(25),1000,1005,995,1000),Bar(t(30),1020,1025,1015,1020)]
    def option_chain(self,index,expiry):
        data=[]
        for strike,delta,bid,ask in ((900,-.25,24.05,24.29),(870,-.08,5,5.05),(860,-.03,1,1.01)):
            key=f'BSE_FO|{strike}P'
            data.append({'expiry':expiry,'strike_price':strike,
                         'call_options':{'instrument_key':'BSE_FO|IV',
                                         'option_greeks':{'iv':24},
                                         'market_data':{}},
                         'put_options':{'instrument_key':key,
                                        'option_greeks':{'delta':delta,'iv':24},
                                        'market_data':{'bid_price':bid,'ask_price':ask,
                                                       'bid_qty':1000,'ask_qty':1000}}})
        return data


def master():
    result=[]
    for strike in (900,870,860):
        result.append({'segment':'BSE_FO','instrument_type':'PE',
                       'underlying_symbol':'SENSEX',
                       'instrument_key':f'BSE_FO|{strike}P',
                       'expiry':'2026-11-12','strike_price':strike,'lot_size':20})
    return result


class AdvancedWorkerTests(unittest.TestCase):
    def test_one_all_day_credit_spread_completes_with_expiry_cutoff(self):
        clock=Clock()
        cfg={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
             'capital_inr':100000,'max_loss_per_trade_inr':500,
             'max_daily_loss_inr':1500,'max_trades_per_day':3,
             'max_allocation_fraction':.25}
        args=SimpleNamespace(market='SENSEX',poll_seconds=30,cooldown_minutes=15,
             master='',directory='',max_quote_age_seconds=15,credit_iv_threshold=18)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            m=root/'master.json'
            m.write_text(json.dumps({'asof':'2026-11-12','records':master()}))
            args.master=str(m)
            args.directory=str(root/'sessions')
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                self.assertEqual(run_advanced(args,cfg,MockApi(clock),clock.clock,clock.sleep),0)
            logs=list(Path(args.directory).glob('*.jsonl'))
            self.assertEqual(len(logs),1)
            entries=[json.loads(line) for line in logs[0].read_text().splitlines()]
            events=[x['event'] for x in entries]
            self.assertIn('INDEX_SIGNAL',events)
            self.assertIn('PAPER_SPREAD_OPEN',events)
            self.assertIn('PAPER_TRADE_CLOSED',events)
            self.assertNotIn('UNRESOLVED_POSITION',events)
            self.assertEqual(events[-1],'SESSION_SUMMARY')
            trade=next(x for x in entries if x['event']=='PAPER_TRADE_CLOSED')
            self.assertEqual(trade['trade_structure'],'TWO_LEG_DEFINED_RISK_CREDIT')
            self.assertEqual(trade['reason'],'TIME_EXIT')
            self.assertLess(trade['net_pnl'],trade['gross_pnl'])
            self.assertTrue(trade['simulated'])


if __name__=='__main__':
    unittest.main()
