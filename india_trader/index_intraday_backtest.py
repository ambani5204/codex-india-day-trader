"""Index-POINTS intraday backtest of the *actual* advanced closed-bar signals.

Deliberately NO put/call, IV, expiry, option lot, executable index orders,
rupee P&L, broker margin or fabricated commissions. Indexes are not directly
tradable; this diagnostic tests direction and structural stop/target placement.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from statistics import median
from collections import Counter, defaultdict
from pathlib import Path

from .core import IST
from .historical_backtest import load_historical_index, replay_signal_day
from .intraday_lab import intraday_signal, ema
from .options_risk import index_stop_plan
from .schedule import market_for_day
from .upstox import UpstoxReader, UpstoxError

FLAT_AT=dt.time(15,10)
COOLDOWN=dt.timedelta(minutes=15)
MAX_TRADES=3
MIN_CHART_RR=1.5


class _LazyHistoricalReader:
    def __init__(self):
        self.reader=None

    def historical_index_candles(self,key,start,end):
        if self.reader is None:
            self.reader=UpstoxReader()
        return self.reader.historical_index_candles(key,start,end)


def _complete_day(bars, day):
    ordered=sorted((b for b in bars if b.time.date()==day),key=lambda b:b.time)
    _,status=replay_signal_day(ordered,day)
    if status!='OK':
        return ordered,status
    # Do not invent fills for days with missing post-signal exit bars. The
    # 15:10 candle is needed to flatten at its OPEN, before market close.
    start=dt.datetime.combine(day,dt.time(9,15),IST)
    end=dt.datetime.combine(day,FLAT_AT,IST)
    by_time={b.time:b for b in ordered}
    clock=start
    while clock<=end:
        if clock not in by_time:
            return ordered,'MISSING_EXIT_OR_SESSION_CANDLES'
        clock+=dt.timedelta(minutes=5)
    return ordered,'OK'


def _exit_price(position,bar,slippage_points):
    """Return (price, reason, exact/estimated exit time), or None.

    A gap across a stop exits at the BAR OPEN, not at the unreachable stop.
    If stop and target touch in one 5m bar, always assume STOP first.
    Intrabar touch time is unknown: cooldown starts from candle CLOSE.
    """
    side=1 if position['direction']=='BULL' else -1
    stop=position['stop']
    target=position['target']
    def adverse(p):
        return p-side*slippage_points
    if bar.time.time()>=FLAT_AT:
        return adverse(bar.open),'TIME_EXIT',bar.time
    if side==1:
        if bar.open<=stop:
            return adverse(bar.open),'GAP_STOP',bar.time
        if bar.open>=target:
            return adverse(bar.open),'GAP_TARGET',bar.time
        stop_hit=bar.low<=stop
        target_hit=bar.high>=target
    else:
        if bar.open>=stop:
            return adverse(bar.open),'GAP_STOP',bar.time
        if bar.open<=target:
            return adverse(bar.open),'GAP_TARGET',bar.time
        stop_hit=bar.high>=stop
        target_hit=bar.low<=target
    estimated_exit=bar.time+dt.timedelta(minutes=5)
    if stop_hit:
        return adverse(stop),('STOP_FIRST_AMBIGUOUS' if target_hit else 'STOP'),estimated_exit
    if target_hit:
        return adverse(target),'TARGET',estimated_exit
    return None


def _policy_signal_guard(closed,signal,policy):
    """Real-time-only market regime gate; no end-of-day labels or future bars.

    Efficiency ratio (Kaufman-style) is low when prices are choppy and high
    for a directional move. Opening range width and candle body are additional
    early-session filters, because ADX/slow EMAs are not yet available at 09:35.
    """
    if not policy:
        return None
    enabled=policy.get('strategies')
    if enabled is not None and signal['strategy'] not in enabled:
        return 'STRATEGY_DISABLED_IN_RESEARCH'
    lookback=int(policy.get('regime_lookback',8))
    threshold=float(policy.get('min_efficiency_ratio',0))
    if not 0<=threshold<=1 or lookback<3 or lookback>40:
        raise ValueError('Invalid regime research parameters')
    prices=[b.close for b in closed]
    n=min(lookback,len(prices)-1)
    if n<3:
        return 'REGIME_INSUFFICIENT_HISTORY'
    changes=[abs(prices[j]-prices[j-1])
             for j in range(len(prices)-n,len(prices))]
    travel=sum(changes)
    efficiency=abs(prices[-1]-prices[-n-1])/travel if travel>0 else 0
    if efficiency<threshold:
        return 'SIDEWAYS_EFFICIENCY_RATIO'
    opening=[b for b in closed if b.time.time() in
             (dt.time(9,15),dt.time(9,20),dt.time(9,25))]
    if len(opening)==3:
        typical=median(x.high-x.low for x in opening)
        ratio=(max(x.high for x in opening)-min(x.low for x in opening))/typical if typical>0 else 0
        if ratio<float(policy.get('min_open_range_to_bar_range',0)):
            return 'OPENING_RANGE_TOO_COMPRESSED'
    if signal['strategy'] in ('OPENING_RANGE_BREAKOUT','EMA_8_21_CROSS'):
        last=closed[-1]
        body=abs(last.close-last.open)/(last.high-last.low) if last.high>last.low else 0
        if body<float(policy.get('min_trend_candle_body',0)):
            return 'WEAK_DIRECTIONAL_CANDLE'
    if policy.get('require_ema_alignment') and len(prices)>=21:
        fast=ema(prices,8)
        slow=ema(prices,21)
        if (signal['direction']=='BULL' and fast<=slow) or (
            signal['direction']=='BEAR' and fast>=slow):
            return 'AGAINST_CURRENT_EMA_TREND'
    return None


def _policy_adjust_target(plan,signal,spot,policy):
    if not policy:
        return plan
    multiplier=float(policy.get('trend_target_r',2.0))
    if not math.isfinite(multiplier) or not 1<=multiplier<=5:
        raise ValueError('Invalid trend target risk multiple')
    if signal['strategy'] not in ('OPENING_RANGE_BREAKOUT','EMA_8_21_CROSS'):
        return plan
    direction=1 if signal['direction']=='BULL' else -1
    price=round(spot+direction*float(plan['index_risk_points'])*multiplier,2)
    if price<=0:
        raise UpstoxError('Repriced trend target would be invalid')
    return {**plan,'index_target':price,
            'index_reward_points':round(abs(price-spot),2),
            'target_basis':'RESEARCH_TREND_TARGET_'+str(multiplier)+'R'}


def simulate_index_day(bars,day,market,slippage_points=0.0,
                       max_trades=MAX_TRADES,min_chart_rr=MIN_CHART_RR,
                       policy=None):
    """Same intraday_signal and index_stop_plan as advanced option paper worker.

    SIGNAL on closed bar -> next bar OPEN -> monitor future OHLC, one position
    max, up to 3 trades/day, 15min cooldown, flat at 15:10 IST.
    """
    if not isinstance(day,dt.date) or market not in ('NIFTY','SENSEX'):
        raise ValueError('Invalid day or market')
    if (not math.isfinite(slippage_points) or slippage_points<0
            or max_trades<1 or int(max_trades)!=max_trades
            or not math.isfinite(min_chart_rr) or min_chart_rr<=0):
        raise ValueError('Invalid index replay assumptions')
    ordered,status=_complete_day(bars,day)
    if status!='OK':
        return {'day':day.isoformat(),'market':market,'status':status,
                'candidate_signals':0,'trades':[],'rejections':{}}

    rejected=Counter()
    trades=[]
    candidate_count=0
    by_candidate=Counter()
    pending=None
    opened=None
    cooldown_until=dt.datetime.combine(day,dt.time(9,15),IST)
    last_bar=None

    for i,bar in enumerate(ordered):
        if bar.time.time()>FLAT_AT:
            break

        # (A) The signal was known at *previous* candle close, never at
        # current candle's open unless that close already happened.
        if pending is not None:
            signal,plan,signal_time=pending
            pending=None
            direction=signal['direction']
            side=1 if direction=='BULL' else -1
            entry=bar.open+side*slippage_points
            stop=float(plan['index_stop'])
            target=float(plan['index_target'])
            risk=side*(entry-stop)
            reward=side*(target-entry)
            if (entry<=0 or risk<=0 or reward<=0 or
                    reward/risk<min_chart_rr):
                rejected['NEXT_OPEN_INVALIDATES_STOP_TARGET_OR_RR']+=1
            elif len(trades)>=max_trades:
                rejected['MAX_DAILY_TRADES']+=1
            elif bar.time<cooldown_until:
                rejected['COOLDOWN']+=1
            elif opened is not None:
                rejected['ACTIVE_POSITION']+=1
            else:
                opened={'day':day.isoformat(),'market':market,
                        'strategy':signal['strategy'],
                        'pattern':signal.get('range_pattern'),
                        'direction':direction,'signal_time':signal_time.isoformat(),
                        'entry_time':bar.time.isoformat(),
                        'entry':round(entry,4),'stop':round(stop,4),
                        'target':round(target,4),'chart_stop_basis':plan['basis'],
                        'chart_target_basis':plan['target_basis'],
                        'risk_points':round(risk,4),
                        'planned_reward_risk':round(reward/risk,4)}

        # (B) 5-minute future high/low path, from the *entry* candle onward.
        if opened is not None:
            result=_exit_price(opened,bar,slippage_points)
            if result is not None:
                exit_price,why,exit_dt=result
                side=1 if opened['direction']=='BULL' else -1
                profit=side*(exit_price-opened['entry'])
                multiple=profit/opened['risk_points']
                opened.update({'exit_time':exit_dt.isoformat(),
                               'exit':round(exit_price,4),
                               'exit_reason':why,
                               'index_points':round(profit,4),
                               'realized_r':round(multiple,5),
                               'outcome':'WIN' if profit>0 else 'LOSS' if profit<0 else 'FLAT'})
                trades.append(opened)
                opened=None
                cooldown_until=exit_dt+COOLDOWN

        # (C) Only newly CLOSED bars may emit the same advanced index signal.
        confirmed=bar.time+dt.timedelta(minutes=5,seconds=1)
        if not dt.time(9,35)<=confirmed.time()<dt.time(14,40):
            continue
        signal=intraday_signal(ordered[:i+1],confirmed,last_bar)
        last_bar=bar.time
        if signal is None:
            continue
        candidate_count+=1
        by_candidate[signal['strategy']]+=1
        if opened is not None:
            rejected['ACTIVE_POSITION']+=1
            continue
        if pending is not None:
            rejected['ENTRY_PENDING']+=1
            continue
        if len(trades)>=max_trades:
            rejected['MAX_DAILY_TRADES']+=1
            continue
        if confirmed<cooldown_until:
            rejected['COOLDOWN']+=1
            continue
        block=_policy_signal_guard(ordered[:i+1],signal,policy)
        if block:
            rejected[block]+=1
            continue
        try:
            plan=index_stop_plan(ordered[:i+1],signal,bar.close,confirmed)
            plan=_policy_adjust_target(plan,signal,bar.close,policy)
        except (UpstoxError,ValueError,KeyError,TypeError):
            rejected['INVALID_TECHNICAL_STOP_OR_TARGET']+=1
            continue
        next_index=i+1
        if next_index>=len(ordered) or ordered[next_index].time!=bar.time+dt.timedelta(minutes=5):
            rejected['NO_NEXT_OPEN']+=1
            continue
        pending=(signal,plan,confirmed)

    if opened is not None or pending is not None:
        # Complete session validation should ensure exits are possible.
        # Do not represent such a session as complete if a trade is still open.
        return {'day':day.isoformat(),'market':market,
                'status':'INTERNAL_UNRESOLVED_REPLAY',
                'candidate_signals':candidate_count,'trades':[],
                'rejections':dict(rejected)}
    return {'day':day.isoformat(),'market':market,'status':'OK',
            'candidate_signals':candidate_count,
            'by_candidate_strategy':dict(by_candidate),
            'trades':trades,'rejections':dict(rejected)}


def _metrics(trades):
    n=len(trades)
    wins=sum(t['index_points']>0 for t in trades)
    losses=sum(t['index_points']<0 for t in trades)
    sum_r=sum(t['realized_r'] for t in trades)
    gross_win_r=sum(max(0,t['realized_r']) for t in trades)
    gross_loss_r=-sum(min(0,t['realized_r']) for t in trades)
    equity=0.0
    peak=0.0
    drawdown=0.0
    for t in trades:
        equity+=t['realized_r']
        peak=max(peak,equity)
        drawdown=min(drawdown,equity-peak)
    return {'trades':n,'wins':wins,'losses':losses,
            'flat':n-wins-losses,
            'win_rate_pct':round(100*wins/n,2) if n else None,
            'sum_r':round(sum_r,4),
            'average_r':round(sum_r/n,4) if n else None,
            'profit_factor_r':round(gross_win_r/gross_loss_r,4) if gross_loss_r else None,
            'max_drawdown_r':round(drawdown,4),
            # Never add SENSEX and NIFTY raw points into one meaningless figure.
            'gross_index_points':(round(sum(t['index_points'] for t in trades),4)
                                  if len({t['market'] for t in trades})<=1 else None),
            'exit_reasons':dict(Counter(t['exit_reason'] for t in trades))}


def backtest_index_intraday(start,end,market='AUTO',reader=None,
                            cache_dir='trader/backtest_cache',out=None,
                            slippage_points=0.0,max_trades=MAX_TRADES,
                            min_chart_rr=MIN_CHART_RR):
    if isinstance(start,str):start=dt.date.fromisoformat(start)
    if isinstance(end,str):end=dt.date.fromisoformat(end)
    if end<start or (end-start).days>730:
        raise ValueError('Date range must be positive and at most 2 years')
    if end>=dt.datetime.now(IST).date():
        raise ValueError('Backtest must end before current India-market date')
    market=market.upper()
    if market not in ('AUTO','NIFTY','SENSEX','BOTH'):
        raise ValueError('Choose AUTO, NIFTY, SENSEX or BOTH')
    if not math.isfinite(slippage_points) or slippage_points<0:
        raise ValueError('slippage_points must be a finite nonnegative number')

    reader=reader or _LazyHistoricalReader()
    markets=['NIFTY','SENSEX'] if market in ('AUTO','BOTH') else [market]
    data={m:load_historical_index(reader,m,start,end,cache_dir) for m in markets}
    days={m:defaultdict(list) for m in markets}
    for name,bars in data.items():
        for b in bars:
            days[name][b.time.date()].append(b)

    dates=[]
    day=start
    while day<=end:
        if day.weekday()<5:
            for name in (markets if market=='BOTH' else
                         [market_for_day(day)] if market=='AUTO' else [market]):
                dates.append(simulate_index_day(days[name][day],day,name,
                            slippage_points,max_trades,min_chart_rr))
        day+=dt.timedelta(days=1)

    valid=[x for x in dates if x['status']=='OK']
    trades=[trade for d in valid for trade in d['trades']]
    trades.sort(key=lambda t:t['entry_time'])
    strategies=sorted(set(t['strategy'] for t in trades) |
                      {'OPENING_RANGE_BREAKOUT','OPENING_RANGE_FAKEOUT',
                       'OPENING_RANGE_TRAP','EMA_8_21_CROSS','MEAN_REVERSION'})
    rejection_counts=Counter()
    for d in valid:rejection_counts.update(d['rejections'])
    by_strategy={name:_metrics([t for t in trades if t['strategy']==name])
                 for name in strategies}
    monthly=sorted(set(t['day'][:7] for t in trades))
    result={
        'kind':'HISTORICAL_INDEX_INTRADAY_CHART_POINTS_NO_OPTIONS_OR_EXECUTABLE_INDEX_ORDERS',
        'from_date':start.isoformat(),'to_date':end.isoformat(),
        'market_mode':market,
        'source':'UPSTOX_V3_REAL_5MIN_INDEX_CANDLES_OR_CACHED_COPIES',
        'signal_function':'india_trader.intraday_lab.intraday_signal',
        'stop_target_function':'india_trader.options_risk.index_stop_plan',
        'assumptions':{
            'entry':'NEXT_5MIN_BAR_OPEN_AFTER_CONFIRMED_SIGNAL',
            'stop_and_target':'STATIC_CHART_POINTS_FROM_SIGNAL_CANDLE',
            'same_bar_stop_and_target':'CONSERVATIVE_STOP_FIRST',
            'gap_through_stop':'EXIT_AT_ADVERSE_BAR_OPEN',
            'max_trades_per_market_day':max_trades,
            'cooldown_minutes':15,
            'session_flat_at':'15:10 IST',
            'minimum_chart_reward_risk_at_entry':min_chart_rr,
            'slippage_points_each_side':slippage_points,
            'brokerage_taxes_margin':'NOT_MODELED_INDEX_IS_NOT_TRADEABLE',
        },
        'sessions_analyzed':len(dates),'complete_sessions':len(valid),
        'excluded_sessions':len(dates)-len(valid),
        'excluded_by_reason':dict(Counter(d['status'] for d in dates if d['status']!='OK')),
        'candidate_signals':sum(d['candidate_signals'] for d in valid),
        'rejected_signals':dict(rejection_counts),
        'overall':_metrics(trades),
        'by_strategy':by_strategy,
        'by_market':{name:_metrics([t for t in trades if t['market']==name])
                     for name in markets},
        'by_month':{name:_metrics([t for t in trades if t['day'].startswith(name)])
                    for name in monthly},
        'net_options_pnl_inr':None,'net_index_order_pnl_inr':None,
        'warning':'This measures INDEX chart direction, entry and static technical exits only. NIFTY/SENSEX index cannot itself be bought or sold. It says nothing about CE/PE, futures fees, margin, theta, option fills or actual rupee profits. Stop/target touch order within a 5m bar is unknown.',
        'trades':trades,
        'sessions':[{k:v for k,v in d.items() if k!='trades'} for d in dates],
    }
    if out:
        path=Path(out)
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        tmp.replace(path)
    return result
