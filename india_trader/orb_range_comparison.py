"""Research-only 15m versus 30m ORB index-candle replay. Never changes live rules."""
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
from .intraday_lab import intraday_signal as original_signal

def thirty_minute_signal(bars, now, last_bar=None):
    now=now.astimezone(IST)
    if now.weekday()>4 or not dt.time(9,45)<=now.time()<dt.time(14,40):
        return None
    closed=sorted((b for b in bars if b.time.date()==now.date()
                   and b.time+dt.timedelta(minutes=5)<=now),key=lambda b:b.time)
    if len(closed)<7 or (last_bar is not None and closed[-1].time<=last_bar):
        return None
    last=closed[-1]
    end=last.time+dt.timedelta(minutes=5)
    if not 0<=(now-end).total_seconds()<=90:
        return None
    opening=[b for b in closed if dt.time(9,15)<=b.time.time()<dt.time(9,45)]
    expected=[dt.time(9,15+i*5) for i in range(6)]
    if len(opening)!=6 or [b.time.time() for b in opening]!=expected:
        return None
    high=max(b.high for b in opening)
    low=min(b.low for b in opening)
    width=high-low
    if width<=0:
        return None
    clearance=.05*width
    previous=closed[-2]
    if last.close>high+clearance and previous.close<=high+clearance:
        direction='BULL'
    elif last.close<low-clearance and previous.close>=low-clearance:
        direction='BEAR'
    else:
        return None
    return {'strategy':'OPENING_RANGE_BREAKOUT','direction':direction,
            'strength':2,'range_pattern':'BREAKOUT',
            'breakout_level':high if direction=='BULL' else low,
            'confirmation':'CLOSED_OUTSIDE_30_MINUTE_OPENING_RANGE',
            'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}

def baseline_orb_only(bars,now,last_bar=None):
    signal=original_signal(bars,now,last_bar)
    return signal if signal and signal['strategy']=='OPENING_RANGE_BREAKOUT' else None

def metrics(trades):
    n=len(trades)
    r=[float(t['realized_r']) for t in trades]
    equity=peak=dd=0.
    for value in r:
        equity+=value
        peak=max(peak,equity)
        dd=min(dd,equity-peak)
    gains=sum(max(0,x) for x in r)
    losses=-sum(min(0,x) for x in r)
    return {'trades':n,'wins':sum(x>0 for x in r),
            'win_rate_pct':round(100*sum(x>0 for x in r)/n,2) if n else None,
            'total_r':round(sum(r),4),'avg_r':round(sum(r)/n,4) if n else None,
            'profit_factor_r':round(gains/losses,4) if losses else None,
            'max_drawdown_r':round(dd,4)}

def run(start,end,cache_dir='trader/backtest_cache',reader=None):
    reader=reader or _LazyHistoricalReader()
    result={'kind':'RESEARCH_ONLY_15M_VS_30M_ORB_INDEX_CHART_REPLAY',
            'period':[start.isoformat(),end.isoformat()],
            'source':'UPSTOX_V3_5MIN_INDEX_CANDLES',
            'option_pnl_inr':None,'live_strategy_modified':False,
            'warning':'Index chart R only; NOT executable option premium or real futures P&L. '
                      'Both variants use next-bar open, existing technical stops, '
                      '1 point adverse entry/exit slippage, stop-first ambiguity.',
            'markets':{}}
    for market in ('NIFTY','SENSEX'):
        bars=load_historical_index(reader,market,start,end,cache_dir)
        grouped=collections.defaultdict(list)
        for bar in bars: grouped[bar.time.date()].append(bar)
        comparison={}
        for name,fn in [('baseline_15m',baseline_orb_only),('candidate_30m',thirty_minute_signal)]:
            sessions=[]
            original=engine.intraday_signal
            try:
                engine.intraday_signal=fn
                day=start
                while day<=end:
                    if day.weekday()<5:
                        sessions.append(simulate_index_day(grouped[day],day,market,
                                                           slippage_points=1.0,max_trades=3))
                    day+=dt.timedelta(days=1)
            finally:
                engine.intraday_signal=original
            valid=[x for x in sessions if x['status']=='OK']
            trades=sorted([t for x in valid for t in x['trades']],key=lambda x:x['entry_time'])
            # Chronological splits are descriptive only, NOT a tuned selection.
            dates=sorted(x['day'] for x in valid)
            cut=int(len(dates)*.8)
            holdout=set(dates[cut:])
            comparison[name]={'complete_days':len(valid),
                              'excluded_days':len(sessions)-len(valid),
                              'candidate_signals':sum(x['candidate_signals'] for x in valid),
                              'all':metrics(trades),
                              'first_80pct':metrics([t for t in trades if t['day'] not in holdout]),
                              'last_20pct':metrics([t for t in trades if t['day'] in holdout]),
                              'rejections':dict(sum((collections.Counter(x['rejections']) for x in valid),collections.Counter()))}
        result['markets'][market]=comparison
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start',default='2025-11-16')
    p.add_argument('--end',default='2026-11-16')
    p.add_argument('--out',default='trader/backtests/orb_15m_vs_30m.json')
    args=p.parse_args()
    start=dt.date.fromisoformat(args.start)
    end=dt.date.fromisoformat(args.end)
    if start>end or end>=dt.datetime.now(IST).date() or (end-start).days>730:
        p.error('Use completed historical dates within two years')
    result=run(start,end)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
