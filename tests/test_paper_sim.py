import datetime as dt
import tempfile
import unittest
from pathlib import Path
from india_trader.core import IST
from india_trader.paper_sim import Quote,PaperEngine,option_fees,breakeven_sell,realistic_fill,replay_csv
from india_trader.report import summary_from_folder


class PaperSimTests(unittest.TestCase):
    def quote(self,minute,sec,bid,ask,bq=500,aq=500):
        return Quote(dt.datetime(2026,11,11,9,minute,sec,tzinfo=IST),bid,ask,bq,aq)

    def engine(self,**kwargs):
        return PaperEngine('NFO:TESTNIFTY2026CE',20,100000,500,**kwargs)

    def test_options_fees_roundtrip_stt_2026(self):
        fees=option_fees(100,120,65,'NFO')
        # 2 * Rs20 brokerage; STT on SELL premium only (0.15%, nearest rupee).
        self.assertEqual(fees['brokerage'],40)
        self.assertEqual(fees['stt'],12)
        self.assertAlmostEqual(fees['exchange_transaction_charge'],5.08,places=2)
        self.assertGreater(fees['total'],50)
        self.assertGreater(breakeven_sell(100,65,'NFO'),100)
        bfo=option_fees(100,120,65,'BFO')
        self.assertLess(bfo['exchange_transaction_charge'],fees['exchange_transaction_charge'])

    def test_full_quote_parse_and_stale_refusal(self):
        q=Quote.from_kite({'timestamp':'2026-11-11 09:35:02','last_price':100,
                          'depth':{'buy':[{'price':99.8,'quantity':300}],
                                   'sell':[{'price':100.2,'quantity':300}]}})
        self.assertEqual(q.ask,100.2)
        e=self.engine()
        rejected=e.process(q,signal=True,now=q.timestamp+dt.timedelta(seconds=30),max_age_seconds=10)
        self.assertEqual(rejected['event'],'QUOTE_REJECTED')
        self.assertIsNone(e.position)

    def test_depth_walk_and_block(self):
        q=Quote.from_kite({'timestamp':'2026-11-11 09:35:02',
                          'depth':{'buy':[{'price':99.5,'quantity':10},{'price':99,'quantity':20}],
                                   'sell':[{'price':100,'quantity':10},{'price':101,'quantity':20}]}})
        self.assertIsNone(realistic_fill(q,'BUY',50))
        self.assertGreater(realistic_fill(q,'BUY',20),100.0)
        self.assertLess(realistic_fill(q,'SELL',20),99.5)

    def test_profitable_net_is_less_than_gross(self):
        e=self.engine()
        self.assertEqual(e.process(self.quote(35,0,99.5,100),signal=True)['event'],'ENTRY_SIGNAL')
        self.assertEqual(e.process(self.quote(35,2,99.7,100.2))['event'],'PAPER_BUY_FILLED')
        self.assertEqual(e.process(self.quote(36,0,131,131.5))['event'],'EXIT_SIGNAL')
        result=e.process(self.quote(36,2,129,129.5))
        self.assertEqual(result['event'],'PAPER_TRADE_CLOSED')
        self.assertGreater(result['net_pnl'],0)
        self.assertLess(result['net_pnl'],result['gross_pnl'])
        self.assertGreater(result['fees']['total'],0)
        self.assertEqual(e.summary()['closed_trades'],1)

    def test_gap_through_stop_and_fees_causes_loss(self):
        e=self.engine()
        e.process(self.quote(35,0,99.5,100),signal=True)
        e.process(self.quote(35,2,99.7,100.2))
        e.process(self.quote(36,0,82,82.5))
        result=e.process(self.quote(36,2,72,72.5))
        self.assertEqual(result['reason'],'STOP')
        self.assertLess(result['sell_price'],e.events[1]['stop'])
        self.assertLess(result['net_pnl'],result['gross_pnl'])
        self.assertLess(result['net_pnl'],0)

    def test_wide_spread_and_no_depth_block(self):
        e=self.engine(max_spread_pct=0.5)
        e.process(self.quote(35,0,98,100),signal=True)
        self.assertEqual(e.process(self.quote(35,2,98,100))['reason'],'WIDE_SPREAD')
        self.assertIsNone(e.position)
        e2=self.engine()
        e2.process(self.quote(35,0,99.7,100),signal=True)
        self.assertEqual(e2.process(self.quote(35,2,99.7,100,500,2))['reason'],'INSUFFICIENT_VISIBLE_DEPTH')

    def test_index_cannot_be_traded(self):
        with self.assertRaises(ValueError):
            PaperEngine('NSE:NIFTY 50',10,100000,500)

    def test_replay_report(self):
        p=Path(__file__).parent.parent/'examples/SYNTHETIC_option_quotes.csv'
        with tempfile.TemporaryDirectory() as d:
            logfile=Path(d)/'one.jsonl'
            summary=replay_csv(p,self.engine(),journal=logfile)
            self.assertEqual(summary['closed_trades'],1)
            report=summary_from_folder(d)
            self.assertEqual(report['closed_trades'],1)
            self.assertLess(report['estimated_net_after_fixed_cost'],report['net_trading_pnl_after_fees'])


if __name__=='__main__':unittest.main()
