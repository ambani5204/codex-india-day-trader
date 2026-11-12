"""Bounded, chronological strategy research. NEVER auto-updates paper/live trading.

Scores chart signals using an explicitly hypothetical one-lot index-FUTURES
COST PROXY. Underlying candles are spot index OHLC, not futures executions;
margin, contract basis, realistic spreads, personal income tax and option
Greeks are NOT known. A positive proxy result is NOT a tradable profit.

Parameters are fitted on training, compared on validation, and checked ONCE
on a subsequent final holdout. A failure returns NO_ROBUST_EDGE; there is no
infinite loop that mines historical data until one curve looks profitable.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
from collections import Counter,defaultdict
from pathlib import Path

from .core import IST
from .historical_backtest import load_historical_index
from .index_intraday_backtest import simulate_index_day, _LazyHistoricalReader
from .schedule import market_for_day
from .upstox import INDICES

STT_CHANGE=dt.date(2026,4,1)
NIFTY_LOT_CHANGE=dt.date(2026,1,1)
NSE_FUT_EXCHANGE_CHANGE=dt.date(2026,3,1)

REGIME_STRATEGIES={
    'ALL':('OPENING_RANGE_BREAKOUT','OPENING_RANGE_FAKEOUT',
           'OPENING_RANGE_TRAP','EMA_8_21_CROSS','MEAN_REVERSION'),
    'DIRECTIONAL':('OPENING_RANGE_BREAKOUT','OPENING_RANGE_TRAP',
                   'EMA_8_21_CROSS'),
    'BREAKOUT_EMA':('OPENING_RANGE_BREAKOUT','EMA_8_21_CROSS'),
    'EMA_ONLY':('EMA_8_21_CROSS',),
}


def futures_cost_proxy(trade):
    """Indicative Upstox 1-lot FUTURES charges applied to SPOT INDEX prices.

    Upstox published schedule (checked Nov 2026):
      brokerage min(₹20, 0.05% turnover) per side,
      futures STT on *sell* 0.02% before 2026-04-01; 0.05% after,
      stamp duty 0.002% on *buy*, NSE exchange fee 0.00173% prior to
      2026-03-01 and 0.00183% thereafter; BSE futures exchange fee nil,
      SEBI ₹10/crore both sides, NSE IPFT ₹0.10/lakh,
      18% GST on brokerage+exchange+IPFT.
    The NIFTY assumed standard lot changes 75 -> 65 in early Jan 2026;
    SENSEX standard lot 20. Historic active expiries may have different lots.
    """
    market=trade['market']
    if market not in ('NIFTY','SENSEX'):
        raise ValueError('Expected NIFTY or SENSEX for futures proxy')
    date=dt.date.fromisoformat(trade['day'])
    lot=(75 if date<NIFTY_LOT_CHANGE else 65) if market=='NIFTY' else 20
    entry=float(trade['entry'])
    exit_=float(trade['exit'])
    if not math.isfinite(entry) or not math.isfinite(exit_) or min(entry,exit_)<=0:
        raise ValueError('Invalid synthetic index prices for cost proxy')
    buy=entry if trade['direction']=='BULL' else exit_
    sell=exit_ if trade['direction']=='BULL' else entry
    buy_turnover=buy*lot
    sell_turnover=sell*lot
    total_turnover=buy_turnover+sell_turnover
    brokerage=min(20.0,buy_turnover*.0005)+min(20.0,sell_turnover*.0005)
    stt=sell_turnover*(.0005 if date>=STT_CHANGE else .0002)
    stamp=buy_turnover*.00002
    if market=='NIFTY':
        exchange=total_turnover*(.0000183 if date>=NSE_FUT_EXCHANGE_CHANGE
                                 else .0000173)
        ipft=total_turnover*.000001
    else:
        exchange=0.0
        ipft=0.0
    sebi=total_turnover*.000001
    gst=.18*(brokerage+exchange+ipft)
    fees=round(brokerage+stt+stamp+exchange+ipft+sebi+gst,2)
    gross=float(trade['index_points'])*lot
    risk=float(trade['risk_points'])*lot
    if risk<=0:
        raise ValueError('Invalid modeled index-risk denominator')
    return {**trade,
            'futures_proxy_lot':lot,
            'futures_proxy_charges_inr':fees,
            'futures_proxy_stt_inr':round(stt,2),
            'futures_proxy_brokerage_inr':round(brokerage,2),
            'futures_proxy_stamp_inr':round(stamp,2),
            'futures_proxy_exchange_inr':round(exchange,2),
            'futures_proxy_gst_inr':round(gst,2),
            'futures_proxy_net_inr':round(gross-fees,2),
            'net_proxy_r':(gross-fees)/risk}


def _performance(trades):
    n=len(trades)
    profits=[t['net_proxy_r'] for t in trades]
    winners=sum(v>0 for v in profits)
    gross_gain=sum(max(0,v) for v in profits)
    gross_loss=-sum(min(0,v) for v in profits)
    equity=0.
    peak=0.
    dd=0.
    for v in profits:
        equity+=v
        peak=max(peak,equity)
        dd=min(dd,equity-peak)
    gross_total_r=sum(float(t['realized_r']) for t in trades)
    fee_total_r=sum(t['futures_proxy_charges_inr']/
                    (t['risk_points']*t['futures_proxy_lot']) for t in trades)
    return {'trades':n,'net_win_rate_pct':round(100*winners/n,2) if n else None,
            'gross_total_r':round(gross_total_r,4),
            'fee_drag_total_r':round(fee_total_r,4),
            'average_fee_drag_r':round(fee_total_r/n,5) if n else None,
            'estimated_futures_proxy_gross_inr':round(
                sum(t['index_points']*t['futures_proxy_lot'] for t in trades),2),
            'net_total_r':round(sum(profits),4),
            'net_avg_r':round(sum(profits)/n,5) if n else None,
            'net_profit_factor':(round(gross_gain/gross_loss,4)
                                 if gross_loss else None),
            'net_max_drawdown_r':round(dd,4),
            'estimated_futures_proxy_total_inr':round(
                sum(t['futures_proxy_net_inr'] for t in trades),2),
            'estimated_futures_proxy_charges_inr':round(
                sum(t['futures_proxy_charges_inr'] for t in trades),2)}


def _eligible(metrics,minimum_trades,profit_factor=1.05):
    """Not a significance test: minimum precommitted out-of-sample gate."""
    return (metrics['trades']>=minimum_trades and
            (metrics['net_avg_r'] or -float('inf'))>0 and
            (metrics['net_profit_factor'] or 0)>=profit_factor and
            metrics['net_max_drawdown_r']>-25)


def _candidate_params(max_configs):
    """Finite, deterministic grid set before inspecting unseen holdout data."""
    if not 1<=max_configs<=96:
        raise ValueError('max_configs must be between 1 and 96')
    generated=[]
    for basket,efficiency,body,target,min_rr in itertools.product(
        REGIME_STRATEGIES,(.25,.45),(.35,.65),(1.5,2.0,2.5),(1.2,1.5)):
        generated.append({
            'basket':basket,'strategies':REGIME_STRATEGIES[basket],
            'min_efficiency_ratio':efficiency,
            'min_trend_candle_body':body,
            'min_open_range_to_bar_range':1.0,
            'regime_lookback':8,
            'require_ema_alignment':True,
            'trend_target_r':target,
            'min_chart_rr':min_rr,
        })
    # Exactly 96 candidates, fixed for comparable reruns.
    return generated[:max_configs]


def simple_playbook_presets():
    """FOUR predetermined research hypotheses, not tuned to a past holdout.

    Single ORB and EMA strategies only. A maximum ONE position per day;
    no traps, fakeouts, mean-reversion or automatic options activity.
    """
    base={'min_open_range_to_bar_range':1.0,
          'regime_lookback':8,
          'require_ema_alignment':True,
          'max_trades_per_day':1,
          'max_fee_r':0.25}
    return [
      {'name':'ORB_TREND_1_5R',**base,
       'strategies':('OPENING_RANGE_BREAKOUT',),
       'min_efficiency_ratio':.25,'min_trend_candle_body':.55,
       'trend_target_r':1.5,'min_chart_rr':1.2,
       'latest_signal_time':'10:45:00'},
      {'name':'ORB_TREND_2R',**base,
       'strategies':('OPENING_RANGE_BREAKOUT',),
       'min_efficiency_ratio':.25,'min_trend_candle_body':.55,
       'trend_target_r':2.0,'min_chart_rr':1.5,
       'latest_signal_time':'10:45:00'},
      {'name':'EMA_TREND_1_5R',**base,
       'strategies':('EMA_8_21_CROSS',),
       'min_efficiency_ratio':.35,'min_trend_candle_body':.45,
       'trend_target_r':1.5,'min_chart_rr':1.2,
       'latest_signal_time':'13:30:00'},
      {'name':'EMA_TREND_2R',**base,
       'strategies':('EMA_8_21_CROSS',),
       'min_efficiency_ratio':.35,'min_trend_candle_body':.45,
       'trend_target_r':2.0,'min_chart_rr':1.5,
       'latest_signal_time':'13:30:00'},
    ]


def _period_days(all_days):
    ordered=sorted(all_days)
    if len(ordered)<35:
        raise ValueError('At least 35 dates required for chronological research split')
    first=max(1,int(.6*len(ordered)))
    second=max(first+1,int(.8*len(ordered)))
    return {'TRAIN':set(ordered[:first]),
            'VALIDATION':set(ordered[first:second]),
            'HOLDOUT':set(ordered[second:])}


def _load_sessions(start,end,market,reader,cache_dir):
    markets=['NIFTY','SENSEX'] if market in ('AUTO','BOTH') else [market]
    history={name:load_historical_index(reader,name,start,end,cache_dir)
             for name in markets}
    by_market={name:defaultdict(list) for name in markets}
    for name,bars in history.items():
        for bar in bars:
            by_market[name][bar.time.date()].append(bar)
    sessions=[]
    date=start
    while date<=end:
        if date.weekday()<5:
            names=markets if market=='BOTH' else [
                market_for_day(date) if market=='AUTO' else market]
            for name in names:
                sessions.append({'day':date,'market':name,
                                 'bars':by_market[name][date]})
        date+=dt.timedelta(days=1)
    return sessions


def _entry_cost_guard(intent,max_fee_r=0.25,latest_signal_time=None):
    """Reject when worst-side estimated round-trip fees exceed a fraction of R.

    Uses only current INDEX price, stop/target, market, direction and date.
    Entry/stop/target are treated as futures-price PROXIES, never quoted fills.
    """
    if latest_signal_time is not None:
        confirmed=dt.datetime.fromisoformat(intent['signal_time']).astimezone(IST)
        if confirmed.time()>dt.time.fromisoformat(latest_signal_time):
            return 'LATE_SIGNAL_OUTSIDE_SIMPLE_WINDOW'
    if not (0<max_fee_r<=1):
        raise ValueError('Simple cost fraction must be in (0,1]')
    proxy=dict(intent,index_points=0)
    stop=futures_cost_proxy({**proxy,'exit':intent['stop']})
    target=futures_cost_proxy({**proxy,'exit':intent['target']})
    risk_rupees=intent['risk_points']*stop['futures_proxy_lot']
    if max(stop['futures_proxy_charges_inr'],
           target['futures_proxy_charges_inr'])>risk_rupees*max_fee_r:
        return 'ESTIMATED_FUTURES_FEES_EXCEED_RISK_FRACTION'
    return None


def _replay_subset(sessions,days,policy,slippage):
    trades=[]
    excluded=Counter()
    rejection=Counter()
    signals=0
    max_trades=int(policy.get('max_trades_per_day',3)) if policy else 3
    cost_guard=None
    if policy and 'max_fee_r' in policy:
        max_fee_r=float(policy['max_fee_r'])
        stop_time=policy.get('latest_signal_time')
        cost_guard=lambda intent:_entry_cost_guard(intent,max_fee_r,stop_time)
    for session in sessions:
        if session['day'] not in days:
            continue
        result=simulate_index_day(session['bars'],session['day'],
                                  session['market'],
                                  slippage_points=slippage,
                                  max_trades=max_trades,
                                  min_chart_rr=policy.get('min_chart_rr',1.5)
                                  if policy else 1.5,
                                  policy=policy,
                                  entry_filter=cost_guard)
        if result['status']!='OK':
            excluded[result['status']]+=1
            continue
        signals+=result['candidate_signals']
        rejection.update(result['rejections'])
        trades.extend(futures_cost_proxy(t) for t in result['trades'])
    trades.sort(key=lambda t:(t['entry_time'],t['market']))
    return {'metrics':_performance(trades),'excluded':dict(excluded),
            'rejections':dict(rejection),'signals':signals,
            'trades':trades}


def run_simple_edge_research(start,end,market='AUTO',reader=None,
                             cache_dir='trader/backtest_cache',out=None,
                             slippage_points=1.0,min_train=24,
                             min_validation=10,min_holdout=10):
    """A small four-rule gate, *not* a historical-profit finding machine.

    Keep the final block for one candidate chosen on training/validation.
    Reusing previously inspected 2025–2026 dates does not make that final
    portion independently out of sample; only subsequent unseen sessions
    and actual tradable quotes can provide forward evidence.
    """
    if isinstance(start,str):start=dt.date.fromisoformat(start)
    if isinstance(end,str):end=dt.date.fromisoformat(end)
    if start>end or (end-start).days>730 or end>=dt.datetime.now(IST).date():
        raise ValueError('Historical dates must be completed and <=2 years')
    market=market.upper()
    if market not in ('AUTO','NIFTY','SENSEX','BOTH'):
        raise ValueError('Unsupported market')
    if not math.isfinite(slippage_points) or not 0<=slippage_points<=10:
        raise ValueError('Slippage must be 0–10 hypothetical index points')
    if any(not isinstance(v,int) or v<1 for v in
           (min_train,min_validation,min_holdout)):
        raise ValueError('Positive minimum sample counts required')
    reader=reader or _LazyHistoricalReader()
    sessions=_load_sessions(start,end,market,reader,cache_dir)
    splits=_period_days(set(x['day'] for x in sessions))
    results=[]
    qualified=[]
    for policy in simple_playbook_presets():
        train=_replay_subset(sessions,splits['TRAIN'],policy,slippage_points)
        validation=_replay_subset(sessions,splits['VALIDATION'],policy,slippage_points)
        train_pass=_eligible(train['metrics'],min_train,profit_factor=1.10)
        valid_pass=_eligible(validation['metrics'],min_validation,
                            profit_factor=1.10)
        row={'playbook':policy['name'],
             'settings':{k:list(v) if isinstance(v,tuple) else v
                         for k,v in policy.items()},
             'train':train['metrics'],'validation':validation['metrics'],
             'train_rejections':train['rejections'],
             'validation_rejections':validation['rejections'],
             'passed_train':train_pass,'passed_validation':valid_pass,
             'eligible_for_holdout':train_pass and valid_pass}
        results.append(row)
        if train_pass and valid_pass:
            # Only pre-holdout performance can influence selection.
            score=min(train['metrics']['net_avg_r'],
                      validation['metrics']['net_avg_r'])
            qualified.append((score,row,policy))
        print('Simple research:',policy['name'],
              'train',train['metrics']['trades'],
              'validation',validation['metrics']['trades'],
              'passed' if train_pass and valid_pass else 'failed',
              flush=True)
    chosen=None
    held=None
    stress=None
    if qualified:
        _,chosen,selected_policy=max(qualified,key=lambda item:item[0])
        held=_replay_subset(sessions,splits['HOLDOUT'],
                            selected_policy,slippage_points)['metrics']
        stressed=_replay_subset(sessions,splits['HOLDOUT'],
                       selected_policy,max(2.0,slippage_points*2))['metrics']
        stress=stressed
        ok=_eligible(held,min_holdout,profit_factor=1.10) and _eligible(
            stressed,min_holdout,profit_factor=1.10)
        status=('SIMPLE_PROXY_GATES_PASSED_NOT_REAL_TRADING_PROOF' if ok
                else 'SIMPLE_HOLDOUT_OR_STRESS_FAILED')
    else:
        status='NO_SIMPLE_STRATEGY_PASSED_VALIDATION'
    result={
      'kind':'SIMPLE_TWO_STRATEGY_RESEARCH_WITH_ESTIMATED_FUTURES_FEES',
      'status':status,'from_date':start.isoformat(),'to_date':end.isoformat(),
      'market':market,'precommitted_configurations':len(results),
      'rules':'Opening-range breakout OR EMA 8/21, one chart trade per day; no sideways entries when recent efficiency is too low; exclude if expected transaction cost >25% of stop risk',
      'splits':{k:{'start':min(v).isoformat(),'end':max(v).isoformat(),
                    'weekday_dates':len(v)} for k,v in splits.items()},
      'results':results,
      'selected_before_holdout':chosen,
      'final_holdout':held,'final_holdout_double_slippage':stress,
      'requirements':{'min_train_trades':min_train,
                      'min_validation_trades':min_validation,
                      'min_holdout_trades':min_holdout,
                      'min_fee_adjusted_profit_factor':1.10,
                      'positive_net_avg_r':True,
                      'max_fee_fraction_of_risk':0.25,
                      'max_one_trade_per_day':True},
      'safe_to_scale':False,'safe_to_deploy_automatically':False,
      'actual_futures_or_options_profit_inr':None,
      'warning':'Only spot INDEX chart trades with a dated FUTURES-cost proxy. Already-inspected 2025-26 dates are NOT pristine out-of-sample data. Cannot establish actual futures/options fills, after-income-tax profitability, liquidity at greater lots or safe capital scaling. Never auto-deploy.',
    }
    if out:
        path=Path(out)
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',
                       encoding='utf-8')
        tmp.replace(path)
    return result


def run_walk_forward_research(start,end,market='AUTO',reader=None,
                              cache_dir='trader/backtest_cache',
                              out=None,max_configs=96,
                              slippage_points=1.0,
                              min_train=24,min_validation=10,
                              min_holdout=10):
    """Finite parameter search; no live settings are modified.

    No holdout result is computed for candidates until one has passed the
    train+validation selection. This avoids simply selecting the most
    profitable curve on the untouched final 20% of the date range.
    """
    if isinstance(start,str):start=dt.date.fromisoformat(start)
    if isinstance(end,str):end=dt.date.fromisoformat(end)
    if start>end or (end-start).days>730 or end>=dt.datetime.now(IST).date():
        raise ValueError('Use completed historical dates, at most 2 years')
    market=market.upper()
    if market not in ('AUTO','NIFTY','SENSEX','BOTH'):
        raise ValueError('Market must be AUTO, NIFTY, SENSEX or BOTH')
    if not math.isfinite(slippage_points) or slippage_points<0 or slippage_points>10:
        raise ValueError('slippage_points must be between 0 and 10')
    if not 1<=max_configs<=96 or any(
        not isinstance(v,int) or v<1 for v in
        (min_train,min_validation,min_holdout)):
        raise ValueError('Invalid bounded research/sampling settings')
    reader=reader or _LazyHistoricalReader()
    sessions=_load_sessions(start,end,market,reader,cache_dir)
    splits=_period_days(set(x['day'] for x in sessions))

    # Baseline uses original signal engine and unchanged stop/target, but
    # fee proxy + 1 index-point-per-side adverse slippage are included.
    baseline={phase:_replay_subset(sessions,days,None,slippage_points)['metrics']
              for phase,days in splits.items()}
    selected=None
    trials=[]
    for n,policy in enumerate(_candidate_params(max_configs),1):
        train=_replay_subset(sessions,splits['TRAIN'],policy,slippage_points)
        train_stats=train['metrics']
        passed_train=_eligible(train_stats,min_train)
        validation=_replay_subset(sessions,splits['VALIDATION'],policy,slippage_points)
        validation_stats=validation['metrics']
        passed_val=passed_train and _eligible(validation_stats,min_validation)
        summary={'trial':n,'settings':{k:(list(v) if isinstance(v,tuple) else v)
                                      for k,v in policy.items()},
                 'train':train_stats,'validation':validation_stats,
                 'train_pass':passed_train,'validation_pass':passed_val,
                 'train_sideways_filtered':train['rejections'].get(
                     'SIDEWAYS_EFFICIENCY_RATIO',0),
                 'validation_sideways_filtered':validation['rejections'].get(
                     'SIDEWAYS_EFFICIENCY_RATIO',0)}
        trials.append(summary)
        if n%12==0 or n==max_configs:
            eligible=sum(1 for item in trials if item['validation_pass'])
            print(f'Research: {n}/{max_configs} predefined scenarios; '
                  f'{eligible} passed training+validation proxy-cost gates',
                  flush=True)
        if passed_val:
            # Choice is based ONLY on TRAIN and VALIDATION results. Holdout
            # cannot influence selection or ranking.
            score=min(train_stats['net_avg_r'],validation_stats['net_avg_r'])
            score*=min(train_stats['trades'],validation_stats['trades'])**.5
            summary['pre_holdout_score']=round(score,6)
            if selected is None or score>selected[0]:
                selected=(score,policy,summary)

    final_holdout=None
    stress=None
    if selected is not None:
        _,policy,selection=selected
        holdout=_replay_subset(sessions,splits['HOLDOUT'],policy,slippage_points)
        final_holdout=holdout['metrics']
        # Additional adverse slippage check is reported, never used to tune
        # or change the chosen trial's parameters.
        stress_points=max(2.0,slippage_points*2)
        stress=_replay_subset(sessions,splits['HOLDOUT'],policy,stress_points)['metrics']
        robust=(_eligible(final_holdout,min_holdout) and
                _eligible(stress,min_holdout))
        conclusion='RESEARCH_GATE_PASSED_HYPOTHETICAL_PROXY_ONLY' if robust else (
            'HOLDOUT_OR_SLIPPAGE_STRESS_FAILED')
        choice={'trial':selection['trial'],'settings':selection['settings'],
                'train':selection['train'],
                'validation':selection['validation']}
    else:
        conclusion='NO_CANDIDATE_PASSED_TRAIN_AND_VALIDATION'
        choice=None
    split_dates={phase:{'first':min(days).isoformat(),
                        'last':max(days).isoformat(),
                        'weekday_dates':len(days)}
                 for phase,days in splits.items()}
    ranked=sorted(trials,key=lambda x:(
        x['validation_pass'],x['validation']['net_avg_r'] or -999,
        x['validation']['trades']),reverse=True)
    result={
      'kind':'BOUNDED_WALK_FORWARD_INDEX_CHART_WITH_FUTURES_TRANSACTION_COST_PROXY',
      'status':conclusion,'from_date':start.isoformat(),'to_date':end.isoformat(),
      'market':market,'trials_run':len(trials),
      'dates':split_dates,
      'preset_rules':'96 fixed grid variants, no unbounded search or live deployment',
      'cost_model':{
        'instrument':'SYNTHETIC_SPOT_INDEX_PRICE_AS_ONE_FUTURES_LOT_PROXY_NOT_EXECUTABLE',
        'historical_lots':'NIFTY proxy 75 before Jan 2026, 65 after; SENSEX proxy 20',
        'stt_on_sell':{'before_2026_04_01':.0002,'from_2026_04_01':.0005},
        'brokerage':'min(Rs20,0.05% turnover) each side',
        'stamp_duty_buy':.00002,
        'nse_futures_exchange_fee':'0.00173% before Mar 2026, 0.00183% after',
        'bse_futures_exchange_fee':'nil (per Upstox schedule)',
        'gst':'18% on brokerage+exchange+IPFT',
        'sebi_fee':'Rs10/crore','nse_ipft':'Rs0.10/lakh',
        'slippage_index_points_each_side':slippage_points,
        'not_included':'income tax, historical futures basis, real futures fills, margin, funding, option Greeks and IV',
        'sources':['https://upstox.com/brokerage-charges/',
                   'https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax'],
      },
      'criteria':{'training_min_trades':min_train,
                  'validation_min_trades':min_validation,
                  'holdout_min_trades':min_holdout,
                  'net_profit_factor_minimum':1.05,
                  'net_average_r_positive':True,
                  'max_drawdown_r_strictly_above':-25,
                  'additional_holdout_stress_points_each_side':max(2.0,slippage_points*2)},
      'baseline_by_split':baseline,
      'selection_without_holdout':choice,
      'selected_holdout':final_holdout,
      'selected_holdout_stress':stress,
      'top_research_candidates':ranked[:5],
      'trials':trials,
      'net_options_pnl_inr':None,
      'real_futures_pnl_inr':None,
      'safe_to_deploy_automatically':False,
      'warning':'No underlying index is directly tradable. The simulated futures cost proxy uses index OHLC instead of contract futures prices and incomplete margin/fill assumptions. Passing this statistical gate does not prove actual after-tax profitability; personal income tax not estimated. Never optimize indefinitely or auto-deploy to real brokerage.',
    }
    if out:
        path=Path(out)
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',
                       encoding='utf-8')
        tmp.replace(path)
    return result
