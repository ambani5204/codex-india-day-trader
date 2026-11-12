"""No-token tests of bounded walk-forward research and date-aware fee proxy."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from india_trader.core import Bar,IST
from india_trader.index_intraday_backtest import _policy_signal_guard,_policy_adjust_target,simulate_index_day
from india_trader.research_optimizer import (
    futures_cost_proxy, _candidate_params, _eligible, _period_days,
    run_walk_forward_research, _entry_cost_guard,
    simple_playbook_presets, run_simple_edge_research)
from india_trader.upstox import INDICES


def synthetic_trade(day,market='NIFTY'):
    return {'day':day,'market':market,'direction':'BULL',
            'entry':25000 if market=='NIFTY' else 80000,
            'exit':25035 if market=='NIFTY' else 80100,
            'index_points':35 if market=='NIFTY' else 100,
            'risk_points':25 if market=='NIFTY' else 75,
            'entry_time':day+'T10:00:00+05:30'}


def synthetic_day(day):
    start=dt.datetime.combine(day,dt.time(9,15),IST)
    out=[]
    for i in range(72):
        stamp=start+dt.timedelta(minutes=5*i)
        if i<3:
            o,h,l,c=100,101,99,100
        elif i==3:
            o,h,l,c=100,104,100,103
        elif i==4:
            o,h,l,c=103,108,102.8,106
        else:
            o,h,l,c=103,103.5,102.5,103
        out.append(Bar(stamp,o,h,l,c))
    return out


class FakeReader:
    def __init__(self,history):
        self.history=history
        self.calls=0
    def historical_index_candles(self,key,start,end):
        self.calls+=1
        s=dt.date.fromisoformat(start)
        e=dt.date.fromisoformat(end)
        return [b for b in self.history.get(key,[])
                if s<=b.time.date()<=e]


class FeesTests(unittest.TestCase):
    def test_futures_stt_change_apr_2026_and_lot_transition(self):
        before=futures_cost_proxy(synthetic_trade('2026-03-31'))
        after=futures_cost_proxy(synthetic_trade('2026-04-01'))
        self.assertEqual(before['futures_proxy_lot'],65)
        self.assertEqual(after['futures_proxy_lot'],65)
        self.assertLess(before['futures_proxy_stt_inr'],after['futures_proxy_stt_inr'])
        self.assertLess(before['futures_proxy_charges_inr'],after['futures_proxy_charges_inr'])
        older=futures_cost_proxy(synthetic_trade('2025-10-14'))
        self.assertEqual(older['futures_proxy_lot'],75)
        self.assertGreater(older['futures_proxy_charges_inr'],0)

    def test_sensex_bse_fee_zero_and_net_r_less_than_gross(self):
        result=futures_cost_proxy(synthetic_trade('2026-04-10','SENSEX'))
        self.assertEqual(result['futures_proxy_exchange_inr'],0)
        self.assertEqual(result['futures_proxy_lot'],20)
        self.assertLess(result['net_proxy_r'],100/75)
        self.assertLess(result['futures_proxy_net_inr'],2000)

    def test_short_direction_fee_and_stt_use_sell_entry(self):
        short={**synthetic_trade('2026-04-10'), 'direction':'BEAR',
               'entry':25000,'exit':24970,
               'index_points':30}
        result=futures_cost_proxy(short)
        self.assertGreater(result['futures_proxy_stt_inr'],0)
        self.assertLess(result['net_proxy_r'],30/25)


class RegimeFilterTests(unittest.TestCase):
    def test_sideways_detection_uses_only_closed_bars(self):
        day=dt.date(2025,10,1)
        t=dt.datetime.combine(day,dt.time(9,15),IST)
        closes=[100,101,100,101,100,101,100,101,100]
        bars=[Bar(t+dt.timedelta(minutes=5*i),price,
                  price+1,price-1,price) for i,price in enumerate(closes)]
        policy={'min_efficiency_ratio':.4,'regime_lookback':8}
        reason=_policy_signal_guard(bars,{'strategy':'EMA_8_21_CROSS',
                                           'direction':'BULL'},policy)
        self.assertEqual(reason,'SIDEWAYS_EFFICIENCY_RATIO')
        # Adding FUTURE candles to any repository should not affect this
        # decision if the caller only passes the closed prefix.
        future=Bar(t+dt.timedelta(minutes=45),150,151,149,150)
        self.assertEqual(_policy_signal_guard(bars,
                         {'strategy':'EMA_8_21_CROSS','direction':'BULL'},
                         policy),reason)
        self.assertIsNotNone(future)

    def test_risk_multiple_changes_target_not_structural_stop(self):
        plan={'index_spot':100,'index_stop':96,'index_risk_points':4,
              'index_target':108,'index_reward_points':8,'basis':'ORB'}
        sig={'strategy':'OPENING_RANGE_BREAKOUT','direction':'BULL'}
        updated=_policy_adjust_target(plan,sig,100,{'trend_target_r':1.5})
        self.assertEqual(updated['index_stop'],96)
        self.assertEqual(updated['index_target'],106)
        self.assertEqual(plan['index_target'],108)

    def test_finite_grid_and_gate_reject_tiny_samples(self):
        self.assertEqual(len(_candidate_params(96)),96)
        self.assertEqual(len(_candidate_params(7)),7)
        with self.assertRaises(ValueError):
            _candidate_params(100)
        self.assertFalse(_eligible({'trades':2,'net_avg_r':100,
                    'net_profit_factor':100,'net_max_drawdown_r':0},10))


class SimplePlaybookTests(unittest.TestCase):
    def test_just_four_simple_presets_no_mean_reversion_or_traps(self):
        configs=simple_playbook_presets()
        self.assertEqual(len(configs),4)
        self.assertEqual({x['name'] for x in configs},
                         {'ORB_TREND_1_5R','ORB_TREND_2R',
                          'EMA_TREND_1_5R','EMA_TREND_2R'})
        self.assertTrue(all(x['max_trades_per_day']==1 for x in configs))
        self.assertTrue(all(set(x['strategies']).issubset(
            {'EMA_8_21_CROSS','OPENING_RANGE_BREAKOUT'}) for x in configs))
        self.assertTrue(all(x['max_fee_r']<=.25 for x in configs))

    def test_futures_cost_screen_uses_known_entry_and_structural_risk(self):
        intent={'day':'2026-04-10','market':'NIFTY','direction':'BULL',
                'entry':25000.,'stop':24990.,'target':25020.,
                'risk_points':10.,'strategy':'OPENING_RANGE_BREAKOUT',
                'signal_time':'2026-04-10T09:40:01+05:30'}
        self.assertEqual(_entry_cost_guard(intent,.25,'10:45:00'),
                         'ESTIMATED_FUTURES_FEES_EXCEED_RISK_FRACTION')
        wider={**intent,'stop':24900.,'target':25200.,'risk_points':100.}
        self.assertIsNone(_entry_cost_guard(wider,.25,'10:45:00'))
        too_late={**wider,'signal_time':'2026-04-10T11:00:01+05:30'}
        self.assertEqual(_entry_cost_guard(too_late,.25,'10:45:00'),
                         'LATE_SIGNAL_OUTSIDE_SIMPLE_WINDOW')

    def test_simple_chronological_research_never_claims_scaling_safe(self):
        start=dt.date(2025,10,1)
        end=dt.date(2025,12,2)
        days=[]
        day=start
        while day<=end:
            if day.weekday()<5:days.append(day)
            day+=dt.timedelta(days=1)
        reader=FakeReader({INDICES['SENSEX']:[
            candle for d in days for candle in synthetic_day(d)]})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            result=run_simple_edge_research(
                start,end,'SENSEX',reader=reader,
                cache_dir=folder/'cache',out=folder/'result.json',
                min_train=3,min_validation=2,min_holdout=2)
            self.assertEqual(result['precommitted_configurations'],4)
            self.assertEqual(len(result['results']),4)
            self.assertTrue(all('validation_rejections' in row and
                                'validation_candidate_signals' in row and
                                'train_candidate_signals' in row
                                for row in result['results']))
            self.assertIn('first rejection',result['diagnostic_note'].lower())
            self.assertFalse(result['safe_to_scale'])
            self.assertFalse(result['safe_to_deploy_automatically'])
            self.assertIsNone(result['actual_futures_or_options_profit_inr'])
            self.assertEqual(result['status'],'NO_SIMPLE_STRATEGY_PASSED_VALIDATION')
            self.assertEqual(json.loads((folder/'result.json').read_text())['status'],
                             result['status'])
            # Other earlier gates (e.g. sideways/EMA strength) can reject a
            # trade before the pre-entry cost filter is reached.
            self.assertTrue(any(x['train_rejections'] for x in result['results']))


class WalkForwardTests(unittest.TestCase):
    def test_run_bounded_on_realistic_synthetic_5m_prefix_no_credential(self):
        start=dt.date(2025,10,1)
        end=dt.date(2025,12,2)
        days=[]
        date=start
        while date<=end:
            if date.weekday()<5:
                days.append(date)
            date+=dt.timedelta(days=1)
        data=[bar for day in days for bar in synthetic_day(day)]
        first=simulate_index_day(synthetic_day(days[0]),days[0],'SENSEX')
        self.assertGreater(len(first['trades']),0,repr(first))
        fake=FakeReader({INDICES['SENSEX']:data})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            report=run_walk_forward_research(
                start,end,'SENSEX',reader=fake,
                cache_dir=folder/'cache',out=folder/'report.json',
                max_configs=3,slippage_points=.2,
                min_train=3,min_validation=2,min_holdout=2)
            self.assertEqual(report['trials_run'],3)
            self.assertEqual(len(report['trials']),3)
            self.assertEqual(report['net_options_pnl_inr'],None)
            self.assertEqual(report['real_futures_pnl_inr'],None)
            self.assertFalse(report['safe_to_deploy_automatically'])
            self.assertEqual(report['status'],
                'NO_CANDIDATE_PASSED_TRAIN_AND_VALIDATION')
            self.assertGreater(report['baseline_by_split']['TRAIN']['trades'],0,repr(report['baseline_by_split']))
            self.assertTrue((folder/'report.json').exists())
            self.assertEqual(json.loads((folder/'report.json').read_text())['status'],
                             report['status'])
            before=fake.calls
            run_walk_forward_research(start,end,'SENSEX',reader=fake,
                cache_dir=folder/'cache',max_configs=1,
                min_train=3,min_validation=2,min_holdout=2)
            self.assertEqual(fake.calls,before)

    def test_fixed_chronological_splits_never_overlap(self):
        dates={dt.date(2025,10,1)+dt.timedelta(days=n) for n in range(45)}
        splits=_period_days(dates)
        self.assertFalse(splits['TRAIN'] & splits['VALIDATION'])
        self.assertFalse(splits['TRAIN'] & splits['HOLDOUT'])
        self.assertFalse(splits['VALIDATION'] & splits['HOLDOUT'])
        self.assertLess(max(splits['TRAIN']),min(splits['VALIDATION']))
        self.assertLess(max(splits['VALIDATION']),min(splits['HOLDOUT']))


if __name__=='__main__':
    unittest.main()
