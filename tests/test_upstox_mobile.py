import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from india_trader.core import IST
from india_trader.dashboard import dashboard_payload
from india_trader.demo import create_demo
from india_trader.paper_sim import PaperEngine, option_fees
from india_trader.upstox import UpstoxError,UpstoxReader,load_today_master,normalize_expiry,quote_from_upstox,select_atm


class UpstoxMobileTests(unittest.TestCase):
    def records(self):
        return [
            {'segment':'NSE_FO','instrument_type':'CE','underlying_symbol':'NIFTY',
             'instrument_key':'NSE_FO|CE1','expiry':'2026-11-26','strike_price':26000,'lot_size':65},
            {'segment':'NSE_FO','instrument_type':'CE','underlying_symbol':'NIFTY',
             'instrument_key':'NSE_FO|CE2','expiry':'2026-11-26','strike_price':25950,'lot_size':65},
            {'segment':'NSE_FO','instrument_type':'PE','underlying_symbol':'NIFTY',
             'instrument_key':'NSE_FO|PE1','expiry':'2026-11-26','strike_price':26000,'lot_size':65},
            {'segment':'BSE_FO','instrument_type':'PE','underlying_symbol':'SENSEX',
             'instrument_key':'BSE_FO|PE1','expiry':'2026-11-26','strike_price':85000,'lot_size':20},
            {'segment':'NSE_FO','instrument_type':'CE','underlying_symbol':'NIFTY',
             'instrument_key':'NSE_FO|OLD','expiry':'2026-11-11','strike_price':26050,'lot_size':65},
        ]

    def test_selects_nearest_unexpired_at_signal_not_index_order(self):
        day=dt.date(2026,11,11)
        result=select_atm(self.records(),'NIFTY','BUY',25996,day)
        self.assertEqual(result['instrument_key'],'NSE_FO|CE1')
        self.assertEqual(result['lot_size'],65)
        self.assertTrue(result['symbol'].endswith('CE'))
        self.assertTrue(result['symbol'].startswith('NFO:'))
        p=select_atm(self.records(),'SENSEX','SELL',85002,day)
        self.assertEqual(p['option_type'],'PE')
        self.assertEqual(p['exchange'],'BFO')

    def test_prevents_expired_and_unknown_contracts(self):
        day=dt.date(2026,11,11)
        with self.assertRaises(UpstoxError):select_atm(self.records()[-1:],'NIFTY','BUY',26050,day)
        with self.assertRaises(UpstoxError):select_atm(self.records(),'NIFTY','SELL',0,day)

    def test_quote_depth_snapshot_and_stale_ltt(self):
        stamp=dt.datetime(2026,11,11,9,37,0,tzinfo=IST)
        q=quote_from_upstox({'timestamp':stamp.isoformat(),'last_trade_time':str(int((stamp-dt.timedelta(seconds=60)).timestamp()*1000)),
                             'depth':{'buy':[{'price':99,'quantity':100},{'price':98,'quantity':100}],
                                      'sell':[{'price':100,'quantity':200}]}, 'last_price':99.5})
        self.assertEqual(q.bid,99)
        self.assertEqual(q.ask_levels,((100.0,200),))
        self.assertEqual((stamp-q.timestamp).total_seconds(),60)
        e=PaperEngine('NFO:SAMPLECE',20,100000,500,fee_profile='UPSTOX')
        self.assertEqual(e.process(q,signal=True,now=stamp,max_age_seconds=10)['event'],'QUOTE_REJECTED')

    def test_missing_or_invalid_depth_blocks_fills(self):
        with self.assertRaises(UpstoxError):
            quote_from_upstox({'timestamp':'2026-11-11T09:35:00+05:30',
                               'depth':{'buy':[{'price':99,'quantity':10}],'sell':[]}})

    def test_quote_reader_maps_response_key_by_instrument_token(self):
        api=UpstoxReader(token='PLACEHOLDER_FOR_OFFLINE_MOCK')
        now=dt.datetime(2026,11,11,9,35,tzinfo=IST).isoformat()
        full={'NSE_FO:TEST':{'instrument_token':'NSE_FO|123','timestamp':now,
                            'depth':{'buy':[{'price':100,'quantity':50}],
                                     'sell':[{'price':101,'quantity':50}]}}}
        with patch.object(api,'get',return_value=full):
            self.assertEqual(api.full_quote('NSE_FO|123').ask,101)
            with self.assertRaises(UpstoxError):api.full_quote('NSE_FO|404')

    def test_parse_candles_from_api_and_sort(self):
        api=UpstoxReader(token='MOCK')
        data={'candles':[['2026-11-11T09:20:00+05:30',100,105,98,103,1000,0],
                         ['2026-11-11T09:15:00+05:30',100,104,99,101,1000,0]]}
        with patch.object(api,'get',return_value=data):
            bars=api.candles('NSE_INDEX|Nifty 50')
        self.assertEqual(bars[0].time.hour,9)
        self.assertEqual(bars[0].time.minute,15)
        self.assertEqual(len(bars),2)

    def test_master_must_be_current_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'master.json'
            p.write_text(json.dumps({'asof':'2026-11-10','records':self.records()}))
            with self.assertRaises(UpstoxError):load_today_master(str(p),dt.date(2026,11,11))

    def test_upstox_option_fees_add_ipft_on_nse(self):
        a=option_fees(100,120,65,'NFO','UPSTOX')
        b=option_fees(100,120,65,'NFO','ZERODHA')
        self.assertGreater(a['total'],b['total'])
        self.assertGreater(a['ipft'],0)
        self.assertEqual(a['stt'],12)

    def test_forward_worker_mock_market_closes_without_real_orders(self):
        from types import SimpleNamespace
        from india_trader.core import Bar
        from india_trader.paper_sim import Quote
        from india_trader.upstox_forward import run_upstox
        class Clock:
            def __init__(self):self.now=dt.datetime(2026,11,11,9,35,2,tzinfo=IST)
            def clock(self):return self.now
            def sleep(self,seconds):self.now+=dt.timedelta(seconds=seconds)
        clock=Clock()
        class MockReader:
            def candles(self,key):
                def bar(minute,high,low,close):
                    return Bar(dt.datetime(2026,11,11,9,minute,tzinfo=IST),min(close,high),high,low,close)
                return [bar(15,101,99,100),bar(20,102,99,101),bar(25,102,100,101),bar(30,105,102,104)]
            def full_quote(self,key):
                h=clock.now
                px=100.0 if h.second<10 else 135.0
                return Quote(h,px-.2,px+.2,800,800,px)
        settings={'paper':True,'allow_live_orders':False,'allow_derivatives':True,'max_daily_loss_inr':2000,
                  'max_trades_per_day':3,'capital_inr':100000,'max_loss_per_trade_inr':1600,
                  'max_allocation_fraction':0.25}
        args=SimpleNamespace(market='NIFTY',lots=1,poll_seconds=5,candle_poll_seconds=30,
            max_minutes=2,max_signal_age_seconds=90,master=None,directory=None,
            fee_profile='UPSTOX',stop_pct=15,target_pct=30,max_spread_pct=2,
            slippage_bps=5,latency_ms=750,max_quote_age_seconds=15)
        with tempfile.TemporaryDirectory() as tmp:
            master=Path(tmp)/'instruments.json'
            master.write_text(json.dumps({'asof':'2026-11-11','records':self.records()}))
            args.master=str(master);args.directory=str(Path(tmp)/'sessions')
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()):
                self.assertEqual(run_upstox(args,settings,MockReader(),clock.clock,clock.sleep),0)
            result=dashboard_payload(args.directory,mode='upstox')
            self.assertEqual(result['report']['closed_trades'],1)
            self.assertFalse(result['is_demo'])
            self.assertGreater(result['report']['gross_trading_pnl_before_fees'],result['report']['net_trading_pnl_after_fees'])
            with redirect_stdout(StringIO()):
                with self.assertRaises(UpstoxError):
                    run_upstox(args,settings,MockReader(),clock.clock,clock.sleep)

    def test_demo_dashboard_synthetic_profit_and_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            created=create_demo(tmp)
            self.assertEqual(len(created),2)
            self.assertTrue(all(x['closed_trades']==1 for x in created))
            report=dashboard_payload(tmp,'demo')
            self.assertTrue(report['is_demo'])
            self.assertEqual(report['report']['closed_trades'],2)
            self.assertEqual(len(report['series']),2)
            self.assertGreater(report['report']['fees_and_taxes'],0)
            self.assertGreater(created[0]['net_pnl'],0)
            self.assertLess(created[1]['net_pnl'],0)

if __name__=='__main__': unittest.main()
