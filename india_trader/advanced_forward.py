"""Experimental all-session Upstox read-only multi-strategy paper workflow.

Analyzes each newly closed 5-minute candle until 14:40 IST, up to configured
daily trade caps. Long option buy/sell is separate from fully hedged, two-leg
credit selling. Does NOT place orders or represent exchange executions.
"""
from __future__ import annotations
import datetime as dt
import json
import time
from pathlib import Path

from .core import IST, parse_time
from .intraday_lab import intraday_signal, select_credit_spread, spread_mark
from .options_risk import index_stop_plan, select_long_risk_managed, adaptive_paper_risk
from .paper_sim import PaperEngine, journal_write
from .upstox import (INDICES, UpstoxReader, UpstoxError,
                     load_today_master, select_atm, select_delta_contract,
                     normalize_expiry)
from .upstox_forward import _daily_risk, _events


def earliest_current_expiry(records,market,today):
    target=INDICES[market]
    group='NSE_FO' if market=='NIFTY' else 'BSE_FO'
    dates=set()
    for r in records:
        if r.get('segment')!=group or r.get('instrument_type') not in ('CE','PE'):
            continue
        if r.get('underlying_key')!=target:
            u=str(r.get('underlying_symbol','')).upper()
            if u not in ({'NIFTY','NIFTY 50'} if market=='NIFTY' else {'SENSEX'}):
                continue
        try:
            day=normalize_expiry(r['expiry'])
            if day>=today:dates.add(day)
        except (ValueError,KeyError,TypeError,OverflowError):
            pass
    if not dates:
        raise UpstoxError('No active expiry found in current instrument master')
    return min(dates).isoformat()


def _chain_iv(chain,spot,direction):
    side='call_options' if direction=='BULL' else 'put_options'
    try:
        nearest=min(chain,key=lambda row:abs(float(row['strike_price'])-spot))
        value=float((nearest.get(side) or {}).get('option_greeks',{}).get('iv'))
        if 0 < value <= 1:
            value*=100  # fractional IV (provider convention can differ)
        return value if 0 < value <= 500 else None
    except (ValueError,TypeError,KeyError,AttributeError):
        return None


def option_structure_priority(signal, atm_iv_pct, credit_iv_threshold=18):
    """Select preference by chart behavior, never by raw unrelated R:R values.

    Directional continuation and trapped-breakout reversals favor bought
    CE/PE. Failed wick sweeps and mean-reversion signals prefer a hedged
    *credit* spread when IV is high enough to consider selling.
    A candidate always has to pass its own fee-adjusted risk/reward and
    available-expiry safeguards; neither order type is guaranteed to qualify.
    """
    strategy=signal.get('strategy')
    recognized={'OPENING_RANGE_BREAKOUT','OPENING_RANGE_FAKEOUT',
                'OPENING_RANGE_TRAP','EMA_8_21_CROSS','MEAN_REVERSION'}
    if strategy not in recognized:
        raise UpstoxError('Unknown strategy cannot choose an option structure')
    if signal.get('direction') not in {'BULL','BEAR'}:
        raise UpstoxError('Unknown direction cannot select CE or PE')
    if not (0<float(atm_iv_pct)<=500 and 0<float(credit_iv_threshold)<500):
        raise UpstoxError('Invalid option IV regime for structure selection')
    if atm_iv_pct<credit_iv_threshold:
        return ['LONG']
    range_rejection=strategy in {'OPENING_RANGE_FAKEOUT','MEAN_REVERSION'}
    return ['CREDIT','LONG'] if range_rejection else ['LONG','CREDIT']


def latest_closed_index_close(api, market, now):
    """Observe only a FRESH, fully closed 5m index candle; otherwise no trigger."""
    bars=api.candles(INDICES[market])
    eligible=[b for b in bars if b.time.date()==now.date() and
              b.time+dt.timedelta(minutes=5)<=now]
    if not eligible:
        return None
    latest=max(eligible,key=lambda b:b.time)
    age=(now-(latest.time+dt.timedelta(minutes=5))).total_seconds()
    return latest.close if 0<=age<315 else None


def index_invalidated(position, index_close):
    if index_close is None:
        return False
    plan=position.get('index_stop_plan') or {}
    stop=plan.get('index_stop')
    if stop is None:
        return False
    direction=position.get('direction')
    return (direction=='BULL' and index_close<=stop) or (direction=='BEAR' and index_close>=stop)


def previous_day_state(folder, day, market, cooldown_minutes=15):
    """Safely resume after completed paper sessions without resetting day limits.

    An earlier same-day no-trade ORB session is allowed. Never continue
    while any same-day journal lacks a final summary or has an open position;
    this also prevents parallel direct CLI starts once a journal exists.
    """
    journals=sorted(folder.glob(f'{day.isoformat()}_*.jsonl'))
    closed=[]
    prior_market_count=0
    for file in journals:
        events=_events(file)
        if not events or not any(e.get('event')=='SESSION_SUMMARY' for e in events):
            raise UpstoxError(f'Prior paper session is unfinished: {file}. Cannot start a second worker.')
        summary=next(e for e in reversed(events) if e.get('event')=='SESSION_SUMMARY')
        if any(e.get('event')=='UNRESOLVED_POSITION' for e in events) or (
                isinstance(summary.get('summary'),dict) and
                summary['summary'].get('open_position')):
            raise UpstoxError(f'Prior session has an unresolved position: {file}')
        if file.name.startswith(day.isoformat()+'_'+market+'_'):
            prior_market_count+=1
        closed.extend(e for e in events if e.get('event')=='PAPER_TRADE_CLOSED')
    net=sum(float(e['net_pnl']) for e in closed)
    consumed=sum(max(0.0,-float(e['net_pnl'])) for e in closed)
    latest=None
    for event in closed:
        if event.get('timestamp'):
            time=parse_time(event['timestamp'])
            latest=time if latest is None or time>latest else latest
    cooldown_until=(latest+dt.timedelta(minutes=cooldown_minutes)) if latest else None
    return {'prior_session_count':len(journals),'prior_market_sessions':prior_market_count,
            'closed_trades':len(closed),'realized_net_pnl':round(net,2),
            'loss_consumed_inr':round(consumed,2),'cooldown_until':cooldown_until}


def run_advanced(args,settings,reader=None,clock=None,sleep=None):
    clock=clock or (lambda:dt.datetime.now(IST))
    sleep=sleep or time.sleep
    now=clock().astimezone(IST)
    if not (settings.get('paper',False) and settings.get('allow_derivatives',False)
            and not settings.get('allow_live_orders',True)):
        raise UpstoxError('Requires derivatives paper simulation and live orders disabled')
    if args.market not in INDICES:
        raise UpstoxError('Only NIFTY/SENSEX supported')
    if not (now.weekday()<5 and dt.time(9,15)<=now.time()<dt.time(15,10)):
        raise UpstoxError('Start between 09:15 and 15:10 IST on a weekday')
    if args.poll_seconds<10:
        raise UpstoxError('Advanced REST chain polling must be >= 10 seconds')
    # Validate the advanced-only risk percent even when the day has no signal.
    adaptive_paper_risk(settings)
    today=now.date()
    records=load_today_master(args.master,today)
    folder=Path(args.directory)
    folder.mkdir(parents=True,exist_ok=True)
    _daily_risk(folder,today,settings)
    prior=previous_day_state(folder,today,args.market,args.cooldown_minutes)
    if prior['closed_trades']>=int(settings['max_trades_per_day']):
        raise UpstoxError('Daily paper trade count limit reached; no continuation')
    if prior['loss_consumed_inr']>=float(settings['max_daily_loss_inr']):
        raise UpstoxError('Daily loss allowance consumed; no continuation')
    jpath=folder/(f'{today}_{args.market}_ADVANCED_{now:%H%M%S%f}.jsonl')
    if jpath.exists():
        raise UpstoxError(f'Advanced journal already exists: {jpath}')
    session={'session':jpath.stem,'market':args.market,
             'source':'UPSTOX_READ_ONLY_REST_V3_AND_OPTION_CHAIN',
             'mode':'EXPERIMENTAL_ALL_DAY_PAPER_NO_EXCHANGE_FILLS',
             'fee_profile':'UPSTOX'}
    def record(event):
        journal_write(jpath,{**session,**event})
    record({'event':'SESSION_START','timestamp':now.isoformat(),
            'capital':settings['capital_inr'],
            'legacy_fixed_trade_limit_inr':settings.get('max_loss_per_trade_inr'),
            'advanced_risk_percent':settings.get('advanced_risk_percent',1.0),
            'prior_sessions':prior['prior_session_count'],
            'prior_closed_trades':prior['closed_trades'],
            'prior_cumulative_loss_inr':prior['loss_consumed_inr'],
            'warning':'All fills hypothetical, REST samples may miss price moves; no broker orders'})
    if prior['prior_session_count']:
        print(f"Resuming same-day PAPER analysis after {prior['prior_session_count']} "
              f"completed session(s), {prior['closed_trades']} closed prior trades. "
              f"Never backfilling missed candles.",flush=True)
    api=reader or UpstoxReader()
    closed=0
    net=0.
    loss_consumed=0.0  # Profitable trades do NOT replenish daily loss allowance.
    prior_closed=prior['closed_trades']
    prior_net=prior['realized_net_pnl']
    prior_consumed=prior['loss_consumed_inr']
    error_count=0
    last_bar=None
    cooldown_until=max(now,prior['cooldown_until']) if prior['cooldown_until'] else now
    pos=None
    engine=None
    try:
        while clock().astimezone(IST).time()<dt.time(15,20):
            now=clock().astimezone(IST)
            if pos:
                try:
                    if pos['kind']=='CREDIT':
                        chain=api.option_chain(INDICES[args.market],pos['contract']['expiry'])
                        # Index data is optional for the index stop. A failed
                        # candles request must NEVER disable credit-price stops.
                        try:
                            index_close=latest_closed_index_close(api,args.market,now)
                        except (UpstoxError,ValueError,KeyError) as exc:
                            index_close=None
                            record({'event':'INDEX_DATA_WARNING','timestamp':now.isoformat(),
                                    'message':str(exc)})
                        mark=spread_mark(pos['contract'],chain,args.market,now,index_close=index_close)
                        if mark['reason']:
                            net+=float(mark['net_pnl'])
                            loss_consumed+=max(0.0,-float(mark['net_pnl']))
                            closed+=1
                            record({'event':'PAPER_TRADE_CLOSED','timestamp':now.isoformat(),
                                    'market':args.market,'symbol':f"SPREAD:{pos['contract']['option_type']}",
                                    'trade_structure':'TWO_LEG_DEFINED_RISK_CREDIT',
                                    'buy_price':pos['contract']['long_ask'],
                                    'sell_price':pos['contract']['short_bid'],
                                    'quantity':pos['contract']['quantity'],
                                    'gross_pnl':round(mark['net_pnl']+mark['fees'],2),
                                    'fees':mark['fees_breakdown'],
                                    'net_pnl':mark['net_pnl'],'reason':mark['reason'],
                                    'short_strike':pos['contract']['short_strike'],
                                    'long_strike':pos['contract']['long_strike'],
                                    'expiry':pos['contract']['expiry'],
                                    'exit_debit':mark['exit_debit'],
                                    'simulated':True,'execution_caveat':mark['source']})
                            pos=None
                            cooldown_until=now+dt.timedelta(minutes=args.cooldown_minutes)
                    else:
                        q=api.full_quote(pos['contract']['instrument_key'])
                        if (now-q.timestamp).total_seconds()>args.max_quote_age_seconds:
                            raise UpstoxError('Option quote stale; exit not manufactured')
                        record({'event':'QUOTE_SNAPSHOT','timestamp':q.timestamp.isoformat(),
                                'captured_at':now.isoformat(),'bid':q.bid,'ask':q.ask,
                                'symbol':pos['contract']['symbol']})
                        try:
                            index_close=latest_closed_index_close(api,args.market,now)
                        except (UpstoxError,ValueError,KeyError) as exc:
                            index_close=None
                            record({'event':'INDEX_DATA_WARNING','timestamp':now.isoformat(),
                                    'message':str(exc)})
                        invalid=index_invalidated(
                            {'index_stop_plan':pos['contract'].get('index_stop_plan'),
                             'direction':'BULL' if pos['contract']['option_type']=='CE' else 'BEAR'},
                            index_close)
                        result=engine.process(q,now=now,
                                              max_age_seconds=args.max_quote_age_seconds,
                                              force_exit_reason='INDEX_STOP' if invalid else None)
                        if result:
                            record(result)
                            if result['event']=='PAPER_TRADE_CLOSED':
                                net+=result['net_pnl']
                                loss_consumed+=max(0.0,-float(result['net_pnl']))
                                closed+=1
                                pos=None
                                engine=None
                                cooldown_until=now+dt.timedelta(minutes=args.cooldown_minutes)
                            elif result['event'] in ('ENTRY_REJECTED','ENTRY_BLOCKED'):
                                pos=None
                                engine=None
                                cooldown_until=now+dt.timedelta(minutes=args.cooldown_minutes)
                except (UpstoxError,ValueError,KeyError) as exc:
                    record({'event':'MARKET_DATA_ERROR','timestamp':now.isoformat(),
                            'message':str(exc)})
                    error_count+=1
                    if error_count>=5:
                        break
                else:
                    error_count=0
            elif (prior_closed+closed<int(settings['max_trades_per_day']) and
                  prior_consumed+loss_consumed<float(settings['max_daily_loss_inr']) and
                  prior_net+net>-float(settings['max_daily_loss_inr']) and now>=cooldown_until):
                try:
                    bars=api.candles(INDICES[args.market])
                    # Store this candle as evaluated regardless of signal.
                    signal=intraday_signal(bars,now,last_bar)
                    filtered=[b for b in bars if b.time.date()==today and
                              b.time+dt.timedelta(minutes=5)<=now]
                    if filtered:
                        last=sorted(filtered,key=lambda x:x.time)[-1]
                        last_bar=last.time
                    if signal:
                        record({'event':'INDEX_SIGNAL','timestamp':now.isoformat(),
                                'strategy':signal['strategy'],
                                'side':'BUY' if signal['direction']=='BULL' else 'SELL',
                                'trigger_time':signal['confirmed_at'],
                                'underlying_key':INDICES[args.market],
                                'underlying_close':last.close,
                                'signal':signal})
                        # Use scenario-specific preference. These structures
                        # have different payoff distributions: their raw net
                        # R:R numbers are not directly rankable as alternatives.
                        expiry=earliest_current_expiry(records,args.market,today)
                        chain=api.option_chain(INDICES[args.market],expiry)
                        iv=_chain_iv(chain,last.close,signal['direction'])
                        if iv is None:
                            raise UpstoxError('No reliable IV; no paper entry')
                        priority=option_structure_priority(signal,iv,args.credit_iv_threshold)
                        budget=adaptive_paper_risk(
                            settings,realized_net=prior_net+net,
                            realized_losses=prior_consumed+loss_consumed)
                        remaining=budget['remaining_daily_loss_inr']
                        effective_settings={**settings,
                            'max_loss_per_trade_inr':budget['trade_risk_cap_inr']}
                        stop_plan=index_stop_plan(bars,signal,last.close,now)
                        record({'event':'RISK_PLAN','timestamp':now.isoformat(),
                                'index_stop_plan':stop_plan,
                                'risk_budget':budget,
                                'remaining_daily_risk_inr':remaining,
                                'max_trade_loss_inr':budget['trade_risk_cap_inr']})
                        record({'event':'STRATEGY_DECISION','timestamp':now.isoformat(),
                                'strategy':signal['strategy'],
                                'trade_structure':priority[0],
                                'structure_priority':priority,
                                'signal_direction':signal['direction'],
                                'atm_iv_pct':round(iv,2),
                                'iv_threshold_pct':args.credit_iv_threshold,
                                'credit_expiry':expiry,
                                'long_expiry_rule':'FIRST_NON_EXPIRING_ELIGIBLE'})
                        rejected=[]
                        for rank,kind in enumerate(priority):
                            next_kind=priority[rank+1] if rank+1<len(priority) else None
                            selection=None
                            contract=None
                            error=None
                            if kind=='CREDIT':
                                if dt.date.fromisoformat(expiry)==today and now.time()>dt.time(13,45):
                                    error='No new expiry-day short spreads after 13:45 IST'
                                else:
                                    try:
                                        selection=select_credit_spread(
                                            records,chain,args.market,signal['direction'],
                                            last.close,today,effective_settings,expiry=expiry,
                                            remaining_daily_loss=remaining,
                                            min_reward_risk=.25,index_stop_plan=stop_plan)
                                    except UpstoxError as exc:
                                        error=str(exc)
                                if selection:
                                    record({'event':'PAPER_SPREAD_OPEN',
                                            'timestamp':now.isoformat(),
                                            'contract':selection,
                                            'estimated_max_loss':selection[
                                                'estimated_max_expiry_loss_after_fees'],
                                            'warning':'Assumes simultaneous fill at visible 2-leg bid/ask; real margin and fills not verified'})
                                    pos={'kind':'CREDIT','contract':selection}
                                    break
                            else:
                                try:
                                    preferred=select_atm(
                                        records,args.market,
                                        'BUY' if signal['direction']=='BULL' else 'SELL',
                                        last.close,today)
                                except UpstoxError as exc:
                                    error=str(exc)
                                if not error:
                                    # API timeouts propagate to the outer exception
                                    # and NEVER masquerade as eligibility rejections.
                                    chain_l=api.option_chain(
                                        INDICES[args.market],preferred['expiry'])
                                    try:
                                        contract=select_long_risk_managed(
                                            records,chain_l,args.market,
                                            signal['direction'],last.close,today,
                                            effective_settings,stop_plan,
                                            preferred['expiry'],target_pct=30,
                                            min_rr=1.5,max_lots=3,
                                            remaining_daily_loss=remaining)
                                    except UpstoxError as exc:
                                        error=str(exc)
                                if contract:
                                    risk_plan=contract['risk_plan']
                                    qty=risk_plan['quantity']
                                    engine=PaperEngine(
                                        contract['symbol'],qty,settings['capital_inr'],
                                        budget['trade_risk_cap_inr'],
                                        max_allocation_fraction=settings['max_allocation_fraction'],
                                        fee_profile='UPSTOX',flat_by=dt.time(15,10),
                                        planned_stop=risk_plan['stop_bid'],
                                        planned_target=risk_plan['target_bid'],
                                        min_net_reward_risk=1.5,
                                        remaining_daily_loss=remaining)
                                    # Never continue to another structure on a
                                    # transport/quote failure: no quote means no
                                    # trustworthy fill or credit-spread fallback.
                                    q=api.full_quote(contract['instrument_key'])
                                    result=engine.process(
                                        q,signal=True,reason=signal['strategy'],
                                        now=now,max_age_seconds=args.max_quote_age_seconds)
                                    if result and result['event']=='ENTRY_SIGNAL':
                                        record({'event':'OPTION_SELECTION',
                                                'timestamp':now.isoformat(),
                                                'contract':contract,
                                                'fallback_from_credit':(
                                                    'CREDIT' in priority[:rank]),
                                                'structure_rank':rank+1})
                                        record(result)
                                        pos={'kind':'LONG','contract':contract}
                                        break
                                    engine=None
                                    error='Option quote invalid or long entry guard rejected'
                            if error:
                                rejected.append(f'{kind}: {error}')
                                record({'event':'STRUCTURE_REJECTED',
                                        'timestamp':now.isoformat(),
                                        'trade_structure':(
                                            'DEFINED_RISK_CREDIT_SPREAD' if kind=='CREDIT'
                                            else 'NON_EXPIRING_LONG_OPTION'),
                                        'reason':error,
                                        'fallback':('TRY_NON_EXPIRING_LONG_OPTION'
                                                    if next_kind=='LONG' else
                                                    'TRY_HEDGED_CREDIT_SPREAD'
                                                    if next_kind=='CREDIT' else None),
                                        'strategy':signal['strategy'],
                                        'note':'No risk, expiry or liquidity rule is waived'})
                        if pos is None:
                            engine=None
                            raise UpstoxError('No eligible structure for signal: '+
                                              '; '.join(rejected))
                        cooldown_until=now+dt.timedelta(minutes=args.cooldown_minutes)
                except (UpstoxError,ValueError,KeyError) as exc:
                    record({'event':'SIGNAL_REJECTED','timestamp':now.isoformat(),
                            'message':str(exc)})
                    error_count+=1
                    if error_count>=8:
                        break
                else:
                    error_count=0
            # The scheduler remains active between 5-minute signals.
            sleep(args.poll_seconds)
    except KeyboardInterrupt:
        record({'event':'USER_STOP','timestamp':clock().astimezone(IST).isoformat()})
    finally:
        now=clock().astimezone(IST)
        if pos is not None:
            record({'event':'UNRESOLVED_POSITION','timestamp':now.isoformat(),
                    'contract':pos['contract'],
                    'warning':'Not marked closed. Manual reconciliation required; do not assume settlement.'})
        record({'event':'SESSION_SUMMARY','timestamp':now.isoformat(),
                'status':'UNRESOLVED' if pos else 'CLOSED_OR_NO_TRADE',
                'summary':{'closed_trades':closed,'realized_net_pnl':round(net,2),
                           'prior_closed_trades':prior_closed,
                           'day_total_closed_trades':prior_closed+closed,
                           'day_cumulative_net_pnl':round(prior_net+net,2),
                           'day_loss_consumed_inr':round(prior_consumed+loss_consumed,2),
                           'open_position':pos}})
    print(json.dumps({'session':session['session'],'closed_trades':closed,
                      'net_pnl':round(net,2),'unresolved':bool(pos),
                      'journal':str(jpath)},indent=2),flush=True)
    return 0
