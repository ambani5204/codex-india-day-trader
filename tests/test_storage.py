"""Offline tests: incremental durable SQLite archive + monthly summaries."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from india_trader.storage import sync_journals, period_report


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.log=self.root/'logs'
        self.log.mkdir()
        self.db=self.root/'paper.sqlite3'
        self.session=self.log/'2026-11-11_SENSEX_091501.jsonl'

    def write(self, *records):
        with self.session.open('a') as f:
            for row in records:
                f.write(json.dumps(row)+'\n')

    def test_import_is_incremental_and_daily_monthly_results_match(self):
        self.write(
            {'event':'SESSION_START','timestamp':'2026-11-11T09:15:01+05:30'},
            {'event':'INDEX_SIGNAL','timestamp':'2026-11-11T09:35:02+05:30',
             'contract':{'symbol':'BFO:SENSEX_80000_2026-11-12_CE','expiry':'2026-11-12',
                         'strike':80000,'option_type':'CE','delta':0.51,'quoted_ask':100}},
            {'event':'QUOTE_SNAPSHOT','timestamp':'2026-11-11T09:35:02+05:30'},
            {'event':'PAPER_TRADE_CLOSED','timestamp':'2026-11-11T09:44:00+05:30',
             'symbol':'BFO:SENSEX_80000_2026-11-12_CE',
             'buy_price':100,'sell_price':110,'quantity':20,
             'gross_pnl':200,'fees':{'total':55},'net_pnl':145,'reason':'TARGET'},
            {'event':'SESSION_SUMMARY','timestamp':'2026-11-11T09:44:01+05:30',
             'summary':{'closed_trades':1,'open_position':None}},
        )
        a=sync_journals(self.log,self.db)
        self.assertEqual(a['trades'],1)
        self.assertEqual(a['events'],4) # raw price snapshots stay in JSONL, not SQLite
        b=sync_journals(self.log,self.db)
        self.assertEqual(b['events'],0)
        self.assertEqual(b['trades'],0)
        day=period_report('day','2026-11-11',self.db)
        month=period_report('month','2026-11',self.db)
        self.assertEqual(day['net_pnl'],145)
        self.assertEqual(month['net_pnl'],145)
        self.assertEqual(day['trades'],1)
        self.assertEqual(day['session_count'],1)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trades').fetchone()[0],1)

    def test_new_lines_append_without_losing_old_entries(self):
        self.write({'event':'SESSION_START','timestamp':'2026-11-11T09:15:01+05:30'})
        sync_journals(self.log,self.db)
        self.write({'event':'SESSION_SUMMARY','timestamp':'2026-11-11T15:25:01+05:30',
                    'summary':{'closed_trades':0,'open_position':None}})
        sync_journals(self.log,self.db)
        r=period_report('month','2026-11',self.db)
        self.assertEqual(r['session_count'],1)
        self.assertEqual(r['trades'],0)
        self.assertEqual(r['sessions'][0]['status'],'NO_TRADE')

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(ValueError):
            period_report('year','2026',self.db)


if __name__=='__main__':
    unittest.main()
