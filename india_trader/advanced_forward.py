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
from .options_risk import index_stop_plan, select_long_risk_managed
from .paper_sim import PaperEngine, journal_write
from .upstox import (INDICES, UpstoxReader, UpstoxError,
                     load_today_master, select_atm, select_delta_contract,
                     normalize_expiry)
from .upstox_forward import _daily_risk


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
    today=now.date()
    records=load_today_master(args.master,today)
    folder=Path(args.directory)
    folder.mkdir(parents=True,exist_ok=True)
    _daily_risk(folder,today,settings)
    if list(folder.glob(today.isoformat()+'_'+args.market+'_*.jsonl')):
        raise UpstoxError('Existing session for this market/date; no duplicates')
    jpath=folder/(f'{today}_{args.market}_ADVANCED_{now:%H%M%S}.jsonl')
    session={'session':jpath.stem,'market':args.market,
             'source':'UPSTOX_READ_ONLY_REST_V3_AND_OPTION_CHAIN',
             'mode':'EXPERIMENTAL_ALL_DAY_PAPER_NO_EXCHANGE_FILLS',
             'fee_profile':'UPSTOX'}
    def record(event):
        journal_write(jpath,{**session,**event})
    record({'event':'SESSION_START','timestamp':now.isoformat(),
            'capital':settings['capital_inr'],'max_loss_per_trade':settings['max_loss_per_trade_inr'],
            'warning':'All fills hypothetical, REST samples may miss price moves; no broker orders'})
    api=reader or UpstoxReader()
    closed=0
    net=0.
    loss_consumed=0.0  # Profitable trades do NOT replenish daily loss allowance.
    error_count=0
    last_bar=None
    cooldown_until=now
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
            elif (closed<int(settings['max_trades_per_day']) and
                  loss_consumed<float(settings['max_daily_loss_inr']) and
                  net>-float(settings['max_daily_loss_inr']) and now>=cooldown_until):
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
                        # Conservative rule: high-IV regime considers hedged premium
                        # selling; lower IV considers buying a long call/put.
                        # Threshold is exploratory, not calibrated/validated.
                        expiry=earliest_current_expiry(records,args.market,today)
                        chain=api.option_chain(INDICES[args.market],expiry)
                        iv=_chain_iv(chain,last.close,signal['direction'])
                        if iv is None:
                            raise UpstoxError('No reliable IV; no paper entry')
                        kind='CREDIT' if iv>=args.credit_iv_threshold else 'LONG'
                        remaining=float(settings['max_daily_loss_inr'])-loss_consumed
                        stop_plan=index_stop_plan(bars,signal,last.close,now)
                        record({'event':'RISK_PLAN','timestamp':now.isoformat(),
                                'index_stop_plan':stop_plan,
                                'remaining_daily_risk_inr':round(remaining,2),
                                'max_trade_loss_inr':settings['max_loss_per_trade_inr']})
                        record({'event':'STRATEGY_DECISION','timestamp':now.isoformat(),
                                'strategy':signal['strategy'],'trade_structure':kind,
                                'atm_iv_pct':round(iv,2),
                                'iv_threshold_pct':args.credit_iv_threshold})
                        if kind=='CREDIT':
                            if dt.date.fromisoformat(expiry)==today and now.time()>dt.time(13,45):
                                raise UpstoxError('No new expiry-day short spreads after 13:45 IST')
                            selection=select_credit_spread(records,chain,args.market,signal['direction'],
                                                           last.close,today,settings,expiry=expiry,
                                                           remaining_daily_loss=remaining,
                                                           min_reward_risk=.25,index_stop_plan=stop_plan)
                            # Assume both legs fill at visible bid/ask instantaneously:
                            # explicitly optimistic, not an exchange fill or margin validation.
                            record({'event':'PAPER_SPREAD_OPEN','timestamp':now.isoformat(),
                                    'contract':selection,'estimated_max_loss':
                                    selection['estimated_max_expiry_loss_after_fees'],
                                    'warning':'Simultaneous 2-leg fill assumed; no actual brokerage or margin'})
                            pos={'kind':'CREDIT','contract':selection}
                        else:
                            # Long option: do not use same-day expiry when settlement
                            # or auto-exercise is not modeled.
                            preferred=select_atm(records,args.market,
                                                    'BUY' if signal['direction']=='BULL' else 'SELL',
                                                    last.close,today)
                            chain_l=api.option_chain(INDICES[args.market],preferred['expiry'])
                            contract=select_long_risk_managed(records,chain_l,args.market,
                                      signal['direction'],last.close,today,settings,
                                      stop_plan,preferred['expiry'],target_pct=30,
                                      min_rr=1.5,max_lots=3,
                                      remaining_daily_loss=remaining)
                            risk_plan=contract['risk_plan']
                            qty=risk_plan['quantity']
                            engine=PaperEngine(contract['symbol'],qty,settings['capital_inr'],
                                  settings['max_loss_per_trade_inr'],
                                  max_allocation_fraction=settings['max_allocation_fraction'],
                                  fee_profile='UPSTOX',flat_by=dt.time(15,10),
                                  planned_stop=risk_plan['stop_bid'],
                                  planned_target=risk_plan['target_bid'],
                                  min_net_reward_risk=1.5,
                                  remaining_daily_loss=remaining)
                            q=api.full_quote(contract['instrument_key'])
                            result=engine.process(q,signal=True,reason=signal['strategy'],
                                                  now=now,max_age_seconds=args.max_quote_age_seconds)
                            if not result or result['event']!='ENTRY_SIGNAL':
                                engine=None
                                raise UpstoxError('Long option entry not permitted by quote/timing guards')
                            record({'event':'OPTION_SELECTION','timestamp':now.isoformat(),
                                    'contract':contract})
                            record(result)
                            pos={'kind':'LONG','contract':contract}
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
                           'open_position':pos}})
    print(json.dumps({'session':session['session'],'closed_trades':closed,
                      'net_pnl':round(net,2),'unresolved':bool(pos),
                      'journal':str(jpath)},indent=2),flush=True)
    return 0
