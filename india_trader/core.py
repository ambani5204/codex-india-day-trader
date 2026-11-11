"""Deterministic Indian-market ORB analytics, sizing, risk and simulations.

All price data is supplied explicitly; no hidden network calls or real orders.
"""
from __future__ import annotations
import csv
import datetime as dt
import math
import random
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
OPEN = dt.time(9, 15)
CLOSE = dt.time(15, 30)
ORB_END = dt.time(9, 30)
ENTRY_CUTOFF = dt.time(14, 45)
INDEX_SYMBOLS = {'NSE:NIFTY 50', 'NSE:NIFTY BANK', 'BSE:SENSEX', 'NSE:NIFTY NEXT 50'}

@dataclass(frozen=True)
class Bar:
    time: dt.datetime  # opening timestamp of candle, in IST
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self):
        if self.time.tzinfo is None:
            raise ValueError('Candles require timezone-aware timestamps')
        if not (0 < self.low <= min(self.open,self.close) <= max(self.open,self.close) <= self.high):
            raise ValueError('Invalid OHLC candle')


def parse_time(value):
    t = dt.datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    return (t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST))


def read_bars(path):
    bars=[]
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            t = row.get('date') or row.get('timestamp') or row.get('time')
            bars.append(Bar(parse_time(t), *(float(row[k]) for k in ('open','high','low','close')),
                            float(row.get('volume') or 0)))
    return sorted(bars, key=lambda x:x.time)


def is_index(symbol, instrument=None):
    if symbol.upper().strip() in INDEX_SYMBOLS: return True
    if instrument and (instrument.get('segment','') == 'INDICES' or instrument.get('instrument_type','').upper()=='INDEX'):
        return True
    return False


def orb_signal(bars, trading_day=None, asof=None, candle_minutes=5):
    """15 minute ORB with *closed* 5m candles, no lookahead. First signal wins.

    09:15, 09:20, 09:25 are opening range bars. First entry trigger is
    a 09:30 bar closing at 09:35. Both bullish and bearish signals supported.
    """
    if not bars: raise ValueError('No bars')
    if candle_minutes != 5: raise ValueError('ORB currently requires 5-minute candles')
    day = dt.date.fromisoformat(trading_day) if isinstance(trading_day,str) else (trading_day or bars[-1].time.date())
    if asof is None:
        asof = dt.datetime.combine(day, CLOSE, IST)
    elif isinstance(asof,str):
        asof = parse_time(asof)
    seq=[b for b in bars if b.time.date()==day and
         b.time + dt.timedelta(minutes=candle_minutes) <= asof]
    opening = [b for b in seq if OPEN <= b.time.time() < ORB_END]
    expected = [dt.time(9,15),dt.time(9,20),dt.time(9,25)]
    if [b.time.time().replace(second=0,microsecond=0) for b in opening] != expected:
        return {'status':'INSUFFICIENT_OPENING_BARS','date':str(day),'asof':asof.isoformat()}
    high=max(b.high for b in opening)
    low=min(b.low for b in opening)
    trigger=next((b for b in seq if ORB_END <= b.time.time() < ENTRY_CUTOFF and (b.close > high or b.close < low)),None)
    base={'date':str(day),'asof':asof.isoformat(),'orb_high':round(high,4),'orb_low':round(low,4),
          'opening_range':round(high-low,4), 'rule':'first closed 5m candle beyond 09:15-09:30 range'}
    if not trigger: return {'status':'EXPIRED' if asof.time() >= dt.time(14,50) else 'WAITING',**base}
    return {'status':'TRIGGERED','side':'BUY' if trigger.close>high else 'SELL',
            'entry_price':trigger.close,'trigger_bar_start':trigger.time.isoformat(),
            'trigger_time':(trigger.time+dt.timedelta(minutes=5)).isoformat(),**base}


def exit_plan(signal, stop_rule='mid', rr=1.5):
    if signal.get('status') != 'TRIGGERED': raise ValueError('No confirmed entry trigger')
    if rr<=0: raise ValueError('Reward/risk must be positive')
    high, low, entry=map(float,(signal['orb_high'],signal['orb_low'],signal['entry_price']))
    side=signal['side']
    mid=(high+low)/2
    stop=mid if stop_rule=='mid' else (low if side=='BUY' else high) if stop_rule=='opposite' else None
    if stop is None: raise ValueError('stop_rule must be mid or opposite')
    risk=(entry-stop) if side=='BUY' else (stop-entry)
    if risk<=0: raise ValueError('Non-positive stop distance')
    target=entry+(risk*rr if side=='BUY' else -risk*rr)
    return {'symbol':signal.get('symbol'),'side':side,'entry_price':entry,'stop_price':round(stop,4),
            'target_price':round(target,4),'risk_per_unit':round(risk,4),'reward_risk':rr,
            'signal_timestamp':signal['trigger_time'],'source':'closed_bar_orb','flat_by':'15:20 IST',
            'disclaimer':'Stop fills are not guaranteed; no bracket/stop orders were placed.'}


def size_position(plan,capital,max_loss, max_allocation=0.25,lot_size=1,allow_short=False):
    if capital<=0 or max_loss<=0: raise ValueError('capital and max_loss must be positive')
    if lot_size<=0 or int(lot_size)!=lot_size: raise ValueError('bad lot size')
    if plan['side']=='SELL' and not allow_short:
        raise ValueError('Short sale disabled; enable explicitly for an eligible tradable instrument')
    per=float(plan['risk_per_unit']); entry=float(plan['entry_price'])
    if per<=0 or entry<=0: raise ValueError('bad plan prices')
    risk_cap=int(max_loss//(per*lot_size))*lot_size
    capital_cap=int((capital*max_allocation)//(entry*lot_size))*lot_size
    qty=min(risk_cap,capital_cap)
    if qty<=0: raise ValueError('No viable position under risk and allocation limits')
    return {'symbol':plan['symbol'],'side':plan['side'],'quantity':qty,'entry_price':entry,
            'stop_price':plan['stop_price'],'target_price':plan['target_price'],
            'estimated_risk':round(qty*per,2),'estimated_notional':round(qty*entry,2),
            'lot_size':lot_size,'product':'CNC' if plan['side']=='BUY' else 'MIS',
            'order_type':'LIMIT','status':'DRAFT','broker':'ZERODHA',
            'note':'Estimates exclude slippage, brokerage, taxes and margin; paper only by default.'}


def risk_check(order,settings, instrument=None, daily_pnl=0, trades_today=0, now=None):
    flags=[]
    symbol=str(order.get('symbol',''))
    if ':' not in symbol: flags.append('symbol must be EXCHANGE:TRADINGSYMBOL')
    if is_index(symbol,instrument): flags.append('index itself cannot be ordered; choose valid tradable constituent or derivative contract')
    exchange=symbol.split(':',1)[0]
    if exchange not in {'NSE','BSE','NFO','BFO'}:flags.append('unsupported exchange')
    if exchange in {'NFO','BFO'} and not settings.get('allow_derivatives',False):flags.append('derivatives disabled')
    if exchange in {'NFO','BFO'} and not instrument:flags.append('derivatives require current instrument-master validation')
    if order.get('side') not in {'BUY','SELL'}:flags.append('bad side')
    if int(order.get('quantity',0))<=0:flags.append('bad quantity')
    if order.get('side')=='SELL' and not settings.get('allow_short',False):flags.append('short/sell orders disabled')
    loss=float(order.get('estimated_risk',0)); exposure=float(order.get('estimated_notional',0))
    if loss<=0 or loss>float(settings['max_loss_per_trade_inr']):flags.append('trade risk exceeds maximum or is invalid')
    if daily_pnl <= -abs(float(settings['max_daily_loss_inr'])): flags.append('daily loss limit reached')
    if trades_today>=int(settings['max_trades_per_day']):flags.append('trade count limit reached')
    if exposure<=0 or exposure>float(settings['capital_inr'])*float(settings['max_allocation_fraction']):flags.append('capital allocation limit exceeded or invalid')
    if instrument:
        lots=int(float(instrument.get('lot_size') or 1))
        if lots<1 or int(order.get('quantity',0))%lots:flags.append('quantity not a multiple of current contract lot size')
        expiry=instrument.get('expiry')
        if expiry and dt.date.fromisoformat(expiry)<dt.datetime.now(IST).date():flags.append('contract expired')
    if now:
        clock=now.astimezone(IST).time()
        if not dt.time(9,15)<=clock<=dt.time(15,20):flags.append('outside normal intraday entry window')
        if now.astimezone(IST).weekday()>4:flags.append('weekend; exchange holiday calendar still must be checked')
    return {'status':'PASS' if not flags else 'BLOCK','reasons':flags,'order':order}


def replay_trade(day_bars, signal, rr=1.5, stop_rule='mid'):
    plan=exit_plan(signal,stop_rule,rr)
    trigger=parse_time(signal['trigger_time'])
    future=[b for b in day_bars if b.time>=trigger and b.time.time()<CLOSE]
    entry,stop,target=plan['entry_price'],plan['stop_price'],plan['target_price']
    # Conservative if both target and stop touched inside same 5m candle.
    for b in future:
        if signal['side']=='BUY':
            stop_hit=b.low<=stop; target_hit=b.high>=target
        else:
            stop_hit=b.high>=stop; target_hit=b.low<=target
        if stop_hit: return 'STOP'
        if target_hit: return 'TARGET'
    return 'TIME_EXIT'


def backtest(bars,rr=1.5,stop_rule='mid'):
    days=sorted({b.time.date() for b in bars})
    outcomes=[]
    for day in days:
        daily=[b for b in bars if b.time.date()==day]
        signal=orb_signal(daily,day)
        if signal['status']=='TRIGGERED':
            outcomes.append({'date':str(day),'outcome':replay_trade(daily,signal,rr,stop_rule),
                             'side':signal['side'],'entry':signal['entry_price']})
    counts={name:sum(x['outcome']==name for x in outcomes) for name in ('TARGET','STOP','TIME_EXIT')}
    return {'days':len(days),'trades':len(outcomes),'counts':counts,'outcomes':outcomes,
            'method':'historical 5-minute intraday ORB, conservative stop-first on ambiguous bars'}


def monte_carlo(bars,iterations=10000,seed=19,steps=60,rr=1.5):
    """Toy empirical time-of-day return bootstrap, NOT forward prediction.

    Sample 5m close-to-close relative price changes from different prior
    sessions per clock-time; returns are not independent in real markets.
    """
    if len({b.time.date() for b in bars})<20:raise ValueError('>=20 historical sessions required')
    bins={}
    for day in sorted({b.time.date() for b in bars}):
        seq=sorted((b for b in bars if b.time.date()==day), key=lambda x:x.time)
        for prev,next_ in zip(seq,seq[1:]):
            if next_.time-prev.time==dt.timedelta(minutes=5) and prev.close>0:
                bins.setdefault(next_.time.time(),[]).append(next_.close/prev.close-1)
    times=sorted(t for t in bins if dt.time(9,35)<=t<dt.time(15,30))[:steps]
    rng=random.Random(seed)
    totals=[]
    for _ in range(iterations):
        r=1.0;lo=hi=1.0
        for t in times:
            r*=1+rng.choice(bins[t]);lo=min(lo,r);hi=max(hi,r)
        totals.append(r-1)
    totals.sort()
    return {'simulation':'time-of-day return resampling; not a price forecast',
            'iterations':iterations,'seed':seed,'sessions':len({b.time.date() for b in bars}),
            'p05_return':round(totals[int(iterations*.05)],6),'median_return':round(totals[iterations//2],6),
            'p95_return':round(totals[min(iterations-1,int(iterations*.95))],6),
            'warning':'Bootstrap ignores tail risk, regime shifts, transaction costs, and intrabar paths.'}
