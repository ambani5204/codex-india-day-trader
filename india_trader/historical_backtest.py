"""Point-in-time historical replay of the SAME index signal function as advanced paper trading.

This is a SIGNAL backtest, not an options P&L backtest: historical Upstox
index candles do not include bid/ask, Greeks, executed fills, or spreads.
Never infer option profits from underlying index moves.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter,defaultdict
from pathlib import Path

from .core import Bar, IST, parse_time
from .intraday_lab import intraday_signal
from .schedule import market_for_day
from .upstox import INDICES, UpstoxReader, UpstoxError


def _bar_to_json(bar):
    return [bar.time.isoformat(),bar.open,bar.high,bar.low,bar.close,bar.volume]


def _bar_from_json(row):
    return Bar(parse_time(str(row[0])),*(float(v) for v in row[1:5]),float(row[5]))


def load_historical_index(reader,market,start,end,cache_dir):
    """Fetch real 5m candles in 27-calendar-day slices; cache for reproducibility."""
    if market not in INDICES:
        raise ValueError('Market must be NIFTY or SENSEX')
    cache=Path(cache_dir)
    cache.mkdir(parents=True,exist_ok=True)
    cursor=start
    bars=[]
    while cursor<=end:
        finish=min(cursor+dt.timedelta(days=26),end)
        target=cache/f'{market}_{cursor}_{finish}_5m.json'
        if target.exists():
            payload=json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(payload,dict) or payload.get('market')!=market or payload.get('source')!='UPSTOX_V3_HISTORICAL':
                raise ValueError(f'Invalid index cache metadata: {target}')
            segment=[_bar_from_json(row) for row in payload['bars']]
            print(f'Cache {market}: {cursor} to {finish}: {len(segment)} candles',flush=True)
        else:
            segment=reader.historical_index_candles(INDICES[market],cursor.isoformat(),finish.isoformat())
            payload={'source':'UPSTOX_V3_HISTORICAL','market':market,'from_date':cursor.isoformat(),
                     'to_date':finish.isoformat(),'interval':'5m','bars':[_bar_to_json(b) for b in segment]}
            temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
            temporary.replace(target)
            print(f'Upstox {market}: {cursor} to {finish}: {len(segment)} candles',flush=True)
        bars.extend(segment)
        cursor=finish+dt.timedelta(days=1)
    times=[b.time for b in bars]
    if len(times)!=len(set(times)):
        raise ValueError('Duplicate historical index candles across cached date chunks')
    return sorted(bars,key=lambda b:b.time)


def replay_signal_day(bars,day):
    """Re-evaluate each newly CLOSED five-minute bar, no future data.

    Uses india_trader.intraday_lab.intraday_signal unchanged, including
    09:35-14:40 cutoff. These are CANDIDATE signals, not filled trades.
    """
    intraday=sorted((b for b in bars if b.time.date()==day),key=lambda b:b.time)
    if not intraday:
        return [],'NO_MARKET_CANDLES'
    open_stamps=[dt.time(9,15),dt.time(9,20),dt.time(9,25)]
    if [b.time.time() for b in intraday if dt.time(9,15)<=b.time.time()<dt.time(9,30)]!=open_stamps:
        return [],'MISSING_OPENING_BARS'
    # A missing 5-minute index candle can change EMA and reversal results.
    # Refuse to present those days as complete, rather than invent candles.
    active=[b for b in intraday if dt.time(9,15)<=b.time.time()<dt.time(14,40)]
    if any((b.time-a.time)!=dt.timedelta(minutes=5) for a,b in zip(active,active[1:])):
        return [],'MISSING_INTRADAY_CANDLES'

    out=[]
    last_evaluated=None
    for bar in intraday:
        asof=bar.time+dt.timedelta(minutes=5,seconds=1)
        if not (dt.time(9,35)<=asof.time()<dt.time(14,40)):
            continue
        signal=intraday_signal(intraday,asof,last_evaluated)
        last_evaluated=bar.time
        if signal:
            out.append({**signal,'index_close':bar.close})
    return out,'OK'


def annual_signal_backtest(start,end,market='AUTO',reader=None,
                           cache_dir='trader/backtest_cache',out=None):
    """Download/replay ACTUAL Upstox 5m index candles for a dated interval."""
    if isinstance(start,str):start=dt.date.fromisoformat(start)
    if isinstance(end,str):end=dt.date.fromisoformat(end)
    if end<start or (end-start).days>730:
        raise ValueError('Date range must be positive and at most two years')
    if end>=dt.datetime.now(IST).date():
        raise ValueError('Historical replay must end before the current India-market date')
    market=market.upper()
    if market not in ('AUTO','NIFTY','SENSEX','BOTH'):
        raise ValueError('Market must be AUTO, NIFTY, SENSEX or BOTH')
    reader=reader or UpstoxReader()
    markets=['NIFTY','SENSEX'] if market in ('AUTO','BOTH') else [market]
    histories={name:load_historical_index(reader,name,start,end,cache_dir) for name in markets}
    days_by_market={name:defaultdict(list) for name in markets}
    for name,bars in histories.items():
        for b in bars:
            days_by_market[name][b.time.date()].append(b)
    summary=[]
    signals=[]
    day=start
    while day<=end:
        if day.weekday()>=5:
            day+=dt.timedelta(days=1)
            continue
        chosen=markets if market=='BOTH' else [market_for_day(day) if market=='AUTO' else market]
        for name in chosen:
            selections,status=replay_signal_day(days_by_market[name][day],day)
            summary.append({'day':day.isoformat(),'market':name,'status':status,
                            'candles':len(days_by_market[name][day]),
                            'candidate_signals':len(selections)})
            signals.extend({'day':day.isoformat(),'market':name,**signal} for signal in selections)
        day+=dt.timedelta(days=1)
    counts=Counter(s['strategy'] for s in signals)
    status_counts=Counter(d['status'] for d in summary)
    result={
        'kind':'HISTORICAL_INDEX_SIGNAL_REPLAY_NO_OPTIONS_TRADES',
        'from_date':start.isoformat(),'to_date':end.isoformat(),'inclusive':True,
        'market_mode':market,'source':'UPSTOX_V3_5MIN_REAL_HISTORICAL_INDEX_CANDLES',
        'algo_function':'india_trader.intraday_lab.intraday_signal',
        'weekday_schedule':'MON,TUE,FRI=NIFTY; WED,THU=SENSEX' if market=='AUTO' else 'ALL_SELECTED_MARKETS',
        'candidate_signals':len(signals),'by_strategy':dict(counts),
        'days_analyzed':len(summary),'days_with_complete_bars':status_counts['OK'],
        'missing_or_incomplete_days':sum(n for k,n in status_counts.items() if k!='OK'),
        'day_status_counts':dict(status_counts),
        'net_options_pnl':None,'option_trades':None,'win_rate_pct':None,
        'why_no_options_pnl':'Historical index OHLC lacks option-chain delta, IV, bid/ask depth, historical lot specifications and tradable spread fills.',
        'warning':'These are raw candidate entry signals. Actual paper trades may be skipped due to open positions, cooldown, option filters and risk. No inferred option fills.',
        'sessions':summary,'signals':signals,
    }
    if out:
        path=Path(out)
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        tmp.replace(path)
    return result
