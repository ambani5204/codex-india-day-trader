import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from india_trader.core import (Bar, IST, backtest, exit_plan, is_index, monte_carlo,
                               orb_signal, replay_trade, risk_check, size_position, read_bars)
from india_trader.feeds import financial_report, insider_summary


def bar(t,o,h,l,c):
    return Bar(dt.datetime.fromisoformat('2026-11-11T'+t+'+05:30'),o,h,l,c)

OPENING=[bar('09:15:00',100,102,99,101),bar('09:20:00',101,103,100,102),bar('09:25:00',102,104,101,103)]
TRIGGER=bar('09:30:00',103,106,103,105)

class CoreTests(unittest.TestCase):
    def signal(self):
        x=orb_signal(OPENING+[TRIGGER],asof='2026-11-11T09:35:00+05:30')
        x['symbol']='NSE:RELIANCE'
        return x
    def test_full_range_first_closed_bar(self):
        x=self.signal()
        self.assertEqual(x['status'],'TRIGGERED')
        self.assertEqual(x['orb_high'],104)
        self.assertEqual(x['orb_low'],99)
        self.assertEqual(x['entry_price'],105)
        self.assertEqual(x['trigger_time'],'2026-11-11T09:35:00+05:30')
    def test_never_use_unclosed_bar(self):
        self.assertEqual(orb_signal(OPENING+[TRIGGER],asof='2026-11-11T09:34:59+05:30')['status'],'WAITING')
    def test_opening_missing_blocks(self):
        self.assertEqual(orb_signal(OPENING[:2]+[TRIGGER],asof='2026-11-11T09:35:00+05:30')['status'],'INSUFFICIENT_OPENING_BARS')
    def test_exit_and_position(self):
        p=exit_plan(self.signal(),rr=2)
        self.assertEqual(p['stop_price'],101.5)
        self.assertEqual(p['target_price'],112)
        p['symbol']='NSE:RELIANCE'
        order=size_position(p,100000,500,max_allocation=0.25)
        self.assertEqual(order['quantity'],142)
        self.assertLessEqual(order['estimated_risk'],500)
    def test_index_block(self):
        self.assertTrue(is_index('BSE:SENSEX'))
        cfg={'capital_inr':100000,'max_allocation_fraction':.25,'max_loss_per_trade_inr':500,'max_daily_loss_inr':1500,'max_trades_per_day':3,'allow_derivatives':False,'allow_short':False}
        order={'symbol':'NSE:NIFTY 50','side':'BUY','quantity':1,'estimated_risk':50,'estimated_notional':20000}
        self.assertEqual(risk_check(order,cfg)['status'],'BLOCK')
    def test_derivatives_block_and_lot_checks(self):
        cfg={'capital_inr':100000,'max_allocation_fraction':.25,'max_loss_per_trade_inr':500,'max_daily_loss_inr':1500,'max_trades_per_day':3,'allow_derivatives':False,'allow_short':False}
        order={'symbol':'NFO:NIFTY26NOVFUT','side':'BUY','quantity':3,'estimated_risk':50,'estimated_notional':20000}
        r=risk_check(order,cfg,{'lot_size':'65','expiry':'2027-11-11','segment':'NFO-FUT'})
        self.assertEqual(r['status'],'BLOCK')
        self.assertTrue(any('multiple' in s for s in r['reasons']))
    def test_stop_first_on_ambiguous_candle(self):
        sig=self.signal();finalbar=bar('09:35:00',105,115,95,108)
        self.assertEqual(replay_trade(OPENING+[TRIGGER,finalbar],sig),'STOP')
    def test_file_and_fundamentals(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'quarter.csv';p.write_text('period,revenue,net_profit,eps\n2026-Q1,100,10,3\n2026-Q2,125,12,4\n')
            self.assertEqual(financial_report(p)['revenue_change_pct'],25.0)
            p2=Path(tmp)/'ins.csv';p2.write_text('disclosure_date,symbol,insider,side,quantity,source_url\n2026-11-10,NSE:ABC,X,BUY,10,https://example.com\n')
            self.assertEqual(insider_summary(p2)['count'],1)
    def test_backtest_smoke(self):
        result=backtest(OPENING+[TRIGGER,bar('09:35:00',105,111,104,109)])
        self.assertEqual(result['trades'],1)
        self.assertEqual(result['counts']['TARGET'],1)

if __name__=='__main__':unittest.main()
