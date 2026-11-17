"""Bounded research-only ORB timeframe and reward/risk grid. No live edits."""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
from .core import IST
from .historical_backtest import load_historical_index
from .index_intraday_backtest import simulate_index_day, _LazyHistoricalReader
from . import index_intraday_backtest as engine

# Precommitted grid; never loop until a lucky profitable curve appears.
RANGES=(5,15,30,45,60)
CONFIRMATIONS=(5,15)
REWARDS=(1.0,1.5,2.0,2.5,3.0)
BUFFERS=(0.0,0.05,0.10)
MAX_TRADES=(1,2)
def signal_factory(range_minutes,confirm_minutes,buffer_ratio):
    def signal(bars,now,last_bar=None):
        now=now.astimezone(IST)
        if now.weekday()>4 or not dt.time(9,25)<=now.time()<dt.time(14,40):
            return None
        closed=sorted((b for b in bars if b.time.date()==now.date() and
                       b.time+dt.timedelta(minutes=5)<=now),key=lambda b:b.time)
        if not closed or (last_bar is not None and closed[-1].time<=last_bar):
            return None
        last=closed[-1]
        end=last.time+dt.timedelta(minutes=5)
        if not 0<=(now-end).total_seconds()<=90:
            return None
        session_start=dt.datetime.combine(now.date(),dt.time(9,15),IST)
        elapsed=int((end-session_start).total_seconds()/60)
        if elapsed<range_minutes+confirm_minutes or (elapsed-range_minutes)%confirm_minutes!=0:
            return None
        opening=[b for b in closed if 0<=int((b.time-session_start).total_seconds()/60)<range_minutes]
        if len(opening)!=range_minutes//5:
            return None
        high=max(b.high for b in opening)
        low=min(b.low for b in opening)
        width=high-low
        if width<=0:return None
        # All confirmation bars must be closed; compare previous block close.
        current=closed[-confirm_minutes//5:]
        if len(current)!=confirm_minutes//5:return None
        if current[0].time!=end-dt.timedelta(minutes=confirm_minutes):return None
        prev_end=current[0].time
        previous=[b for b in closed if b.time<prev_end]
        if not previous:return None
        clearance=buffer_ratio*width
        if current[-1].close>high+clearance and previous[-1].close<=high+clearance:
            direction='BULL'
        elif current[-1].close<low-clearance and previous[-1].close>=low-clearance:
            direction='BEAR'
        else:return None
        return {'strategy':'OPENING_RANGE_BREAKOUT','direction':direction,
                'strength':2,'range_pattern':'BREAKOUT',
                'breakout_level':high if direction=='BULL' else low,
                'confirmation':'RESEARCH_ORB_%s_%s'%(range_minutes,confirm_minutes),
                'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    return signal

def stats(trades):
    n=len(trades)
    r=[float(t['realized_r']) for t in trades]
    gains=sum(max(x,0) for x in r)
    losses=-sum(min(x,0) for x in r)
    equity=peak=dd=0.0
    for x in r:
        equity+=x;peak=max(peak,equity);dd=min(dd,equity-peak)
    return {'trades':n,'win_rate_pct':round(100*sum(x>0 for x in r)/n,2) if n else None,
            'net_r':round(sum(r),4),'avg_r':round(sum(r)/n,4) if n else None,
            'profit_factor':round(gains/losses,4) if losses else None,
            'max_drawdown_r':round(dd,4)}
def run(start,end,cache_dir):
    reader=_LazyHistoricalReader()
    result={'kind':'RESEARCH_ONLY_BOUNDED_ORB_TIMEFRAME_RR_SWEEP',
            'dates':[start.isoformat(),end.isoformat()],
            'parameters':{'opening_minutes':RANGES,'confirmation_minutes':CONFIRMATIONS,
                          'target_r':REWARDS,'range_buffer_ratio':BUFFERS,
                          'max_trades_day':MAX_TRADES},
            'criteria':{'holdout_win_rate_gt_50':True,'holdout_net_r_gt_0':True,
                        'holdout_profit_factor_gt_1_1':True,'min_holdout_trades':30},
            'warning':'Index-chart R only; excludes option premiums, spread, option fees, theta and real fills. '
                      'Last 20% is untouched for ranking, but reviewing many holdouts can still overfit. '
                      'No real or live paper settings modified.',
            'markets':{}}
    for market in ('NIFTY','SENSEX'):
        candles=load_historical_index(reader,market,start,end,cache_dir)
        days=collections.defaultdict(list)
        for bar in candles:days[bar.time.date()].append(bar)
        dates=sorted(days)
        valid_dates=[d for d in dates if d.weekday()<5]
        cut=int(len(valid_dates)*.8)
        train=set(valid_dates[:cut]);holdout=set(valid_dates[cut:])
        trials=[]
        for opening in RANGES:
          for confirmation in CONFIRMATIONS:
           for buffer in BUFFERS:
            fn=signal_factory(opening,confirmation,buffer)
            old=engine.intraday_signal
            try:
             engine.intraday_signal=fn
             # Replay each signal/entry configuration once for each RR and daily trade cap.
             for rr in REWARDS:
              for max_day in MAX_TRADES:
               policy={'strategies':('OPENING_RANGE_BREAKOUT',),
                       'min_efficiency_ratio':0,'regime_lookback':8,
                       'trend_target_r':rr}
               outputs=[simulate_index_day(days[d],d,market,slippage_points=1.0,
                                           max_trades=max_day,min_chart_rr=1.0,
                                           policy=policy) for d in valid_dates]
               complete=[x for x in outputs if x['status']=='OK']
               trades=[t for x in complete for t in x['trades']]
               a=stats([t for t in trades if dt.date.fromisoformat(t['day']) in train])
               b=stats([t for t in trades if dt.date.fromisoformat(t['day']) in holdout])
               trials.append({'opening_min':opening,'confirmation_min':confirmation,
                              'buffer_ratio':buffer,'target_r':rr,
                              'max_trades_day':max_day,'train':a,'holdout':b,
                              'complete_sessions':len(complete),
                              'candidate_signals':sum(x['candidate_signals'] for x in complete)})
            finally:
             engine.intraday_signal=old
        # Selection based on training only; holdout evaluated for transparency, not tuning.
        ranked=sorted(trials,key=lambda t:(
            t['train']['trades']>=80,
            (t['train']['avg_r'] if t['train']['avg_r'] is not None else -999),
            t['train']['trades']),reverse=True)
        selected=ranked[0]
        passing=[t for t in trials if t['holdout']['trades']>=30 and
                 (t['holdout']['win_rate_pct'] or 0)>50 and
                 t['holdout']['net_r']>0 and
                 (t['holdout']['profit_factor'] or 0)>1.1]
        result['markets'][market]={'trials':len(trials),'training_selected':selected,
                                  'passing_holdout_count_DESCRIPTIVE_NOT_SELECTION':len(passing),
                                  'top_training_candidates':ranked[:15],
                                  'all_trials':trials}
        print(market,'trials',len(trials),'training selected',selected,flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start',default='2025-11-16')
    p.add_argument('--end',default='2026-11-16')
    p.add_argument('--out',default='trader/backtests/orb_timeframe_rr_grid.json')
    a=p.parse_args()
    start=dt.date.fromisoformat(a.start);end=dt.date.fromisoformat(a.end)
    if start>end or end>=dt.datetime.now(IST).date() or (end-start).days>730:
        p.error('Completed historical dates within two years required')
    result=run(start,end,'trader/backtest_cache')
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print('Wrote',dest)
if __name__=='__main__':main()
