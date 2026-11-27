"""Offline integration test for experimental all-day credit spreads with no real API calls."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from india_trader.core import Bar, IST
from india_trader.paper_sim import Quote
from india_trader.advanced_forward import run_advanced, previous_day_state
from india_trader.upstox import UpstoxError


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
        start=dt.datetime(2026,11,12,9,15,tzinfo=IST)
        bars=[Bar(start+dt.timedelta(minutes=5*i),1000,1005,995,1000)
              for i in range(11)]
        bars.append(Bar(start+dt.timedelta(minutes=55),1020,1025,1015,1020))
        return bars
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


class ExpiryFallbackApi:
    """14:00 expiry-day breakout: short spreads prohibited, next expiry long valid."""
    def __init__(self, clock, allow_long=True):
        self.clock=clock
        self.allow_long=allow_long

    def candles(self,index):
        start=dt.datetime(2026,11,12,9,15,tzinfo=IST)
        bars=[]
        for i in range(57):  # 09:15 through 13:55, full 5m bars
            time=start+dt.timedelta(minutes=5*i)
            if i==56:
                bars.append(Bar(time,1040,1065,1020,1060))
            else:
                bars.append(Bar(time,1000,1005,995,1000))
        return bars

    def option_chain(self,index,expiry):
        if expiry=='2026-11-12':
            return [{'expiry':expiry,'strike_price':1060,
                     'call_options':{'instrument_key':'BSE_FO|CURRENT_CE',
                                     'option_greeks':{'iv':24},
                                     'market_data':{}},
                     'put_options':{'option_greeks':{'iv':24}}}]
        if expiry=='2026-11-19':
            return [{'expiry':expiry,'strike_price':1050,
                     'call_options':{'instrument_key':'BSE_FO|NEXT_CE',
                                     'option_greeks':{'delta':.5,'iv':24},
                                     'market_data':{'bid_price':99,'ask_price':100,
                                                    'bid_qty':1000 if self.allow_long else 0,
                                                    'ask_qty':1000 if self.allow_long else 0}}}]
        raise AssertionError('unexpected option-chain expiry '+expiry)

    def full_quote(self,instrument_key):
        if instrument_key!='BSE_FO|NEXT_CE':
            raise AssertionError('Wrong long instrument '+instrument_key)
        now=self.clock.clock()
        return Quote(now,99,100,1000,1000)


def expiry_fallback_master():
    return [
      {'segment':'BSE_FO','instrument_type':'CE',
       'underlying_symbol':'SENSEX','instrument_key':'BSE_FO|CURRENT_CE',
       'expiry':'2026-11-12','strike_price':1060,'lot_size':20},
      {'segment':'BSE_FO','instrument_type':'CE',
       'underlying_symbol':'SENSEX','instrument_key':'BSE_FO|NEXT_CE',
       'expiry':'2026-11-19','strike_price':1050,'lot_size':20},
    ]


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
        clock.now=dt.datetime(2026,11,12,10,15,2,tzinfo=IST)
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


    def test_expiry_credit_cutoff_attempts_qualified_next_expiry_long(self):
        clock=Clock()
        clock.now=dt.datetime(2026,11,12,14,0,2,tzinfo=IST)
        config={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
                'capital_inr':100000,'max_loss_per_trade_inr':500,
                'advanced_risk_percent':1.0,
                'max_daily_loss_inr':1500,'max_trades_per_day':3,
                'max_allocation_fraction':.25}
        args=SimpleNamespace(market='SENSEX',poll_seconds=30,cooldown_minutes=15,
            master='',directory='',max_quote_age_seconds=15,credit_iv_threshold=18)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            m=root/'master.json'
            m.write_text(json.dumps({'asof':'2026-11-12',
                                     'records':expiry_fallback_master()}))
            args.master=str(m)
            args.directory=str(root/'journals')
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                self.assertEqual(run_advanced(args,config,ExpiryFallbackApi(clock),
                                              clock.clock,clock.sleep),0)
            file=next(Path(args.directory).glob('*.jsonl'))
            events=[json.loads(line) for line in file.read_text().splitlines()]
            kinds=[x['event'] for x in events]
            self.assertIn('STRATEGY_DECISION',kinds)
            decision=next(x for x in events if x['event']=='STRATEGY_DECISION')
            self.assertEqual(decision['structure_priority'],['LONG','CREDIT'])
            self.assertNotIn('STRUCTURE_REJECTED',kinds)
            self.assertIn('OPTION_SELECTION',kinds)
            contract=next(x['contract'] for x in events if x['event']=='OPTION_SELECTION')
            self.assertEqual(contract['expiry'],'2026-11-19')
            self.assertEqual(contract['option_type'],'CE')
            self.assertFalse(next(x for x in events if x['event']=='OPTION_SELECTION')['fallback_from_credit'])
            self.assertLessEqual(contract['risk_plan']['estimated_stop_loss_including_charges'],1000)
            self.assertGreaterEqual(contract['risk_plan']['net_reward_risk'],1.5)
            self.assertIn('PAPER_TRADE_CLOSED',kinds)
            self.assertNotIn('PAPER_SPREAD_OPEN',kinds)

    def test_expiry_credit_fallback_rejects_unliquid_long_without_faking_trades(self):
        clock=Clock()
        clock.now=dt.datetime(2026,11,12,14,0,2,tzinfo=IST)
        config={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
                'capital_inr':100000,'max_loss_per_trade_inr':500,
                'advanced_risk_percent':1.0,
                'max_daily_loss_inr':1500,'max_trades_per_day':3,
                'max_allocation_fraction':.25}
        args=SimpleNamespace(market='SENSEX',poll_seconds=30,cooldown_minutes=15,
            master='',directory='',max_quote_age_seconds=15,credit_iv_threshold=18)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            m=root/'master.json'
            m.write_text(json.dumps({'asof':'2026-11-12',
                                     'records':expiry_fallback_master()}))
            args.master=str(m)
            args.directory=str(root/'journals')
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                self.assertEqual(run_advanced(args,config,ExpiryFallbackApi(clock,False),
                                              clock.clock,clock.sleep),0)
            file=next(Path(args.directory).glob('*.jsonl'))
            events=[json.loads(line) for line in file.read_text().splitlines()]
            kinds=[x['event'] for x in events]
            self.assertIn('STRUCTURE_REJECTED',kinds)
            self.assertIn('SIGNAL_REJECTED',kinds)
            rejected=[x for x in events if x['event']=='STRUCTURE_REJECTED']
            self.assertEqual([x['trade_structure'] for x in rejected],
                             ['NON_EXPIRING_LONG_OPTION','DEFINED_RISK_CREDIT_SPREAD'])
            self.assertIn('13:45',rejected[1]['reason'])
            self.assertNotIn('OPTION_SELECTION',kinds)
            self.assertNotIn('PAPER_TRADE_CLOSED',kinds)
            self.assertNotIn('PAPER_SPREAD_OPEN',kinds)


    def test_start_advanced_at_1125_after_0915_no_trade_orb_session(self):
        """Exact November 12 Android issue: earlier completed ORB must not block."""
        clock=Clock()
        clock.now=dt.datetime(2026,11,12,11,25,2,tzinfo=IST)
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
            folder=Path(args.directory)
            folder.mkdir()
            old=folder/'2026-11-12_SENSEX_091503.jsonl'
            old.write_text('\n'.join([
                json.dumps({'event':'SESSION_START','timestamp':'2026-11-12T09:15:03+05:30'}),
                json.dumps({'event':'SESSION_SUMMARY','timestamp':'2026-11-12T09:40:37+05:30',
                            'status':'CLOSED_OR_NO_TRADE',
                            'summary':{'closed_trades':0,'realized_net_pnl':0.,
                                       'open_position':None}})
            ])+'\n')
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                self.assertEqual(run_advanced(args,cfg,MockApi(clock),clock.clock,clock.sleep),0)
            sessions=sorted(folder.glob('*.jsonl'))
            self.assertEqual(len(sessions),2)
            advanced=next(p for p in sessions if '_ADVANCED_' in p.name)
            events=[json.loads(line) for line in advanced.read_text().splitlines()]
            self.assertEqual(events[0]['prior_closed_trades'],0)
            self.assertEqual(events[0]['prior_sessions'],1)
            self.assertEqual(events[-1]['event'],'SESSION_SUMMARY')
            self.assertFalse(any(e['event']=='PAPER_TRADE_CLOSED' for e in events))

    def test_prior_unfinished_session_blocks_new_paper_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=root/'2026-11-12_SENSEX_091503.jsonl'
            old.write_text(json.dumps({'event':'SESSION_START',
                        'timestamp':'2026-11-12T09:15:03+05:30'})+'\n')
            with self.assertRaises(UpstoxError) as caught:
                previous_day_state(root,dt.date(2026,11,12),'SENSEX')
            self.assertIn('unfinished',str(caught.exception))

    def test_unfinished_nifty_does_not_block_sensex(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'2026-11-18_NIFTY_ADVANCED_092032101922.jsonl').write_text(
                json.dumps({'event':'SESSION_START'})+'\n')
            state=previous_day_state(root,dt.date(2026,11,18),'SENSEX')
            self.assertEqual(state['prior_session_count'],0)
            self.assertEqual(state['closed_trades'],0)
            with self.assertRaises(UpstoxError):
                previous_day_state(root,dt.date(2026,11,18),'NIFTY')

    def test_prior_realized_loss_and_cooldown_carry_forward(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=root/'2026-11-12_SENSEX_091503.jsonl'
            closed=[
               {'event':'SESSION_START','timestamp':'2026-11-12T09:15:03+05:30'},
               {'event':'PAPER_TRADE_CLOSED','timestamp':'2026-11-12T10:45:00+05:30',
                'net_pnl':-350.25},
               {'event':'PAPER_TRADE_CLOSED','timestamp':'2026-11-12T11:05:00+05:30',
                'net_pnl':200.00},
               {'event':'SESSION_SUMMARY','timestamp':'2026-11-12T11:06:00+05:30',
                'summary':{'closed_trades':2,'open_position':None}}
            ]
            old.write_text('\n'.join(json.dumps(e) for e in closed)+'\n')
            state=previous_day_state(root,dt.date(2026,11,12),'SENSEX',15)
            self.assertEqual(state['closed_trades'],2)
            self.assertEqual(state['realized_net_pnl'],-150.25)
            self.assertEqual(state['loss_consumed_inr'],350.25)
            self.assertEqual(state['cooldown_until'],
                             dt.datetime(2026,11,12,11,20,tzinfo=IST))



class SessionSplitTimeTests(unittest.TestCase):
    """CHG-20261127-1605: env-configurable session end + flat-by for the two-job split."""

    def test_env_time_parsing_and_guard(self):
        from india_trader.advanced_forward import _env_time, UpstoxError
        import os
        self.assertEqual(_env_time('X_UNSET_ENV', dt.time(15,30)), dt.time(15,30))
        for bad in ('1', '12345', '2500', '1270', 'abcd'):
            os.environ['X_T']=bad
            try:
                with self.assertRaises(UpstoxError):
                    _env_time('X_T', dt.time(15,30))
            finally:
                os.environ.pop('X_T', None)
        os.environ['X_T']='1215'
        try:
            self.assertEqual(_env_time('X_T', dt.time(15,30)), dt.time(12,15))
        finally:
            os.environ.pop('X_T', None)

    def test_morning_half_ends_cleanly_and_afternoon_continues_day_counters(self):
        import os
        cfg={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
             'capital_inr':100000,'max_loss_per_trade_inr':500,
             'max_daily_loss_inr':1500,'max_trades_per_day':3,'max_allocation_fraction':.25}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); m=root/'master.json'
            m.write_text(json.dumps({'asof':'2026-11-12','records':master()}))
            directory=str(root/'sessions')
            def mk():
                return SimpleNamespace(market='SENSEX',poll_seconds=30,cooldown_minutes=15,
                    master=str(m),directory=directory,max_quote_age_seconds=15,credit_iv_threshold=18)
            from io import StringIO
            from contextlib import redirect_stdout
            # MORNING: stop at 10:00, flat-by 10:00. No open position may survive.
            c1=Clock(); c1.now=dt.datetime(2026,11,12,9,35,2,tzinfo=IST)
            os.environ['PAPER_SESSION_END']='1000'; os.environ['PAPER_FLAT_BY']='1000'
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(run_advanced(mk(),cfg,MockApi(c1),c1.clock,c1.sleep),0)
            finally:
                os.environ.pop('PAPER_SESSION_END',None); os.environ.pop('PAPER_FLAT_BY',None)
            morning=sorted(Path(directory).glob('2026-11-12_SENSEX_*.jsonl'))
            self.assertEqual(len(morning),1)
            mev=[json.loads(l) for l in morning[0].read_text().splitlines()]
            summ=next(e for e in reversed(mev) if e['event']=='SESSION_SUMMARY')
            # Morning session closed cleanly: no open position carried past its end.
            self.assertIsNone(summ['summary']['open_position'])
            self.assertFalse(any(e['event']=='UNRESOLVED_POSITION' for e in mev))
            # the morning loop must have stopped by 10:00
            self.assertLess(dt.datetime.fromisoformat(summ['timestamp']).time(), dt.time(10,1))
            # AFTERNOON: fresh session later the same day continues (restart gate allows it)
            c2=Clock(); c2.now=dt.datetime(2026,11,12,13,0,2,tzinfo=IST)
            os.environ['PAPER_SESSION_END']='1520'
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(run_advanced(mk(),cfg,MockApi(c2),c2.clock,c2.sleep),0)
            finally:
                os.environ.pop('PAPER_SESSION_END',None)
            allsess=sorted(Path(directory).glob('2026-11-12_SENSEX_*.jsonl'))
            self.assertEqual(len(allsess),2)  # morning + afternoon, both clean
            aev=[json.loads(l) for l in allsess[-1].read_text().splitlines()]
            start=next(e for e in aev if e['event']=='SESSION_START')
            # afternoon inherits the morning's completed-session count
            self.assertGreaterEqual(start['prior_sessions'],1)


if __name__=='__main__':
    unittest.main()
