"""Offline diagnostics and chart-target regression coverage."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from india_trader.diagnostics import diagnose_paper_sessions
from india_trader.options_risk import size_long_option
from india_trader.upstox import UpstoxError


CFG={'paper':True,'allow_live_orders':False,'allow_derivatives':True,
     'capital_inr':100000,'max_loss_per_trade_inr':500,
     'max_daily_loss_inr':1500,'max_allocation_fraction':.25}


class SetupTargetTests(unittest.TestCase):
    def test_bought_option_target_uses_index_setup_delta_not_fixed_30pct(self):
        plan={'index_risk_points':10,'index_reward_points':20,
              'index_spot':1000,'index_stop':990,
              'index_target':1020,'target_basis':'ORB_2R_PROJECTION'}
        p=size_long_option(100,99,.5,20,'BFO',CFG,plan,
                           target_pct=30,min_rr=.1,max_lots=1)
        self.assertEqual(p['target_bid'],109)
        self.assertEqual(p['stop_bid'],94)
        self.assertEqual(p['target_basis'],'INDEX_STRUCTURE_DELTA')
        self.assertLessEqual(p['estimated_stop_loss_including_charges'],500)

    def test_structural_target_too_close_fails_instead_of_fallback_30pct(self):
        plan={'index_risk_points':10,'index_reward_points':1,
              'index_spot':1000,'index_stop':990,'index_target':1001}
        with self.assertRaises(UpstoxError):
            size_long_option(100,99,.5,20,'BFO',CFG,plan,
                             target_pct=30,min_rr=.1,max_lots=1)


class DiagnosticTests(unittest.TestCase):
    def test_reports_real_rejection_events_without_claiming_trades(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            events=[
                {'event':'SESSION_START','timestamp':'2026-11-12T11:33:00+05:30'},
                {'event':'INDEX_SIGNAL','strategy':'EMA_8_21_CROSS',
                 'timestamp':'2026-11-12T12:05:00+05:30'},
                {'event':'RISK_PLAN','timestamp':'2026-11-12T12:05:00+05:30',
                 'remaining_daily_risk_inr':1500,
                 'index_stop_plan':{'basis':'EMA_6_BAR_SWING_WITH_ATR_BUFFER',
                                    'index_stop':1012,'index_target':994,
                                    'index_risk_points':6,'index_reward_points':12,
                                    'target_basis':'EMA_2R_TREND_PROJECTION'}},
                {'event':'SIGNAL_REJECTED','message':'One full lot exceeds INR risk limit',
                 'timestamp':'2026-11-12T12:05:02+05:30'},
                {'event':'SESSION_SUMMARY','summary':{'open_position':None},
                 'timestamp':'2026-11-12T15:20:00+05:30'},
            ]
            (folder/'2026-11-12_SENSEX_ADVANCED_113300.jsonl').write_text(
                '\n'.join(json.dumps(e) for e in events)+'\n',encoding='utf-8')
            d=diagnose_paper_sessions(folder,'2026-11-12','SENSEX')
            self.assertEqual(d['journal_files'],1)
            self.assertEqual(d['signals'],1)
            self.assertEqual(d['signals_by_strategy']['EMA_8_21_CROSS'],1)
            self.assertEqual(d['closed_trades'],0)
            self.assertEqual(d['risk_plans'],1)
            self.assertEqual(d['rejections'][0]['count'],1)
            self.assertEqual(d['recent_risk_plans'][0]['index_stop'],1012)
            self.assertEqual(d['pending_or_unresolved_sessions'],0)

    def test_credit_fallback_report_separates_attempts_from_paper_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            rows=[
              {'event':'SESSION_START','timestamp':'2026-11-13T10:00:00+05:30'},
              {'event':'INDEX_SIGNAL','strategy':'EMA_8_21_CROSS'},
              {'event':'RISK_PLAN','max_trade_loss_inr':1000,
               'risk_budget':{'risk_percent':1.0,'trade_risk_cap_inr':1000}},
              {'event':'STRUCTURE_REJECTED','reason':'No liquid OTM hedge',
               'trade_structure':'DEFINED_RISK_CREDIT_SPREAD',
               'fallback':'TRY_NON_EXPIRING_LONG_OPTION'},
              {'event':'OPTION_SELECTION','fallback_from_credit':True,
               'contract':{'option_type':'CE'}},
              {'event':'SESSION_SUMMARY','summary':{'open_position':None}},
            ]
            (folder/'2026-11-13_NIFTY_ADVANCED_100000.jsonl').write_text(
                '\n'.join(json.dumps(x) for x in rows)+'\n',encoding='utf-8')
            result=diagnose_paper_sessions(folder,'2026-11-13','NIFTY')
            self.assertEqual(result['credit_structure_rejections'],1)
            self.assertEqual(result['long_fallback_attempts'],1)
            self.assertEqual(result['long_fallback_selections'],1)
            self.assertEqual(result['long_option_fills'],0)
            self.assertEqual(result['recent_risk_plans'][0]['max_trade_loss_inr'],1000)
            self.assertEqual(result['recent_risk_plans'][0]['risk_budget']['risk_percent'],1.0)
            self.assertEqual(result['closed_trades'],0)
            self.assertEqual(result['rejections'],[])

    def test_active_journal_is_marked_pending_not_represented_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'2026-11-12_SENSEX_ADVANCED_113300.jsonl').write_text(
                json.dumps({'event':'SESSION_START'})+'\n',encoding='utf-8')
            d=diagnose_paper_sessions(folder,'2026-11-12','SENSEX')
            self.assertEqual(d['pending_or_unresolved_sessions'],1)


if __name__=='__main__':
    unittest.main()
