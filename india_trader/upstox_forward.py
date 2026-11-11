"""Live REST-snapshot forward-paper trading for NIFTY/SENSEX via Upstox.

The only network functions invoked are Upstox GET market-data endpoints.
There are NO order APIs. One market/one process at a time; daily OAuth required.
"""
from __future__ import annotations
import datetime as dt
import json
import time
from pathlib import Path
from .core import IST, orb_signal, parse_time
from .paper_sim import PaperEngine, journal_write
from .upstox import INDICES, UpstoxReader, UpstoxError, load_today_master, select_atm, select_delta_contract


def _events(path):
    if not path.exists():return []
    events=[]
    with path.open(encoding='utf8') as f:
        for line in f:
            try:events.append(json.loads(line))
            except ValueError:pass
    return events


def _daily_risk(directory, day, settings, market=None):
    closed=[]
    pattern=day.isoformat()+'_'+(market+'_' if market else '')+'*.jsonl'
    for file in Path(directory).glob(pattern):
        events=_events(file)
        if any(e.get('event')=='PAPER_BUY_FILLED' for e in events) and not any(e.get('event')=='PAPER_TRADE_CLOSED' for e in events):
            raise UpstoxError(f'Unresolved position: {file}. Review before another session')
        closed.extend(e for e in events if e.get('event')=='PAPER_TRADE_CLOSED')
    if sum(float(e['net_pnl']) for e in closed)<=-float(settings['max_daily_loss_inr']):
        raise UpstoxError('Daily loss limit reached')
    if len(closed)>=int(settings['max_trades_per_day']):
        raise UpstoxError('Maximum trades per day reached')


def run_upstox(args,settings,reader=None,clock=None,sleep=None):
    """One real-time session. Injectable time/reader enable deterministic offline tests."""
    clock=clock or (lambda:dt.datetime.now(IST))
    sleep=sleep or time.sleep
    if args.market not in INDICES:raise UpstoxError('Only NIFTY and SENSEX supported')
    if not settings.get('paper',True) or settings.get('allow_live_orders',False):
        raise UpstoxError('Simulation requires paper=true, allow_live_orders=false')
    if not settings.get('allow_derivatives',False):
        raise UpstoxError('Set allow_derivatives=true for paper options simulation (no live orders)')
    now=clock().astimezone(IST)
    if now.weekday()>4 or not dt.time(9,15)<=now.time()<dt.time(15,10):
        raise UpstoxError('Market session requires weekday 09:15-15:10 IST; exchange holidays need calendar validation')
    if args.lots<1 or args.poll_seconds<3 or args.candle_poll_seconds<10:
        raise UpstoxError('Invalid sizing or poll interval')
    day=now.date()
    cache=args.master
    records=load_today_master(cache,day)
    directory=Path(args.directory)
    _daily_risk(directory,day,settings,market=args.market if settings.get('_paper_market_partitions',1)==2 else None)
    # Fail closed after existing session on this trading day: no duplicate signal.
    prior=list(directory.glob(day.isoformat()+'_'+args.market+'_*.jsonl'))
    if prior:raise UpstoxError('A '+args.market+' forward-paper session already exists today; inspect previous journal before restarting')
    api=reader or UpstoxReader()
    path=directory/(day.isoformat()+'_'+args.market+'_'+now.strftime('%H%M%S')+'.jsonl')
    session_until=min(now+dt.timedelta(minutes=args.max_minutes),dt.datetime.combine(day,dt.time(15,25),IST))
    session_id=day.isoformat()+'_'+args.market+'_'+now.strftime('%H%M%S')
    base={'session':session_id,'market':args.market,'source':'UPSTOX_REST_V3_SNAPSHOTS',
          'mode':'FORWARD_PAPER_NOT_BROKER_EXECUTIONS','fee_profile':args.fee_profile}
    def write(evt):
        journal_write(path,{**base,**evt})
    write({'event':'SESSION_START','timestamp':now.isoformat(),'capital':settings['capital_inr'],
           'max_loss_per_trade':settings['max_loss_per_trade_inr'],
           'market_partitions':settings.get('_paper_market_partitions',1),
           'slippage_bps':args.slippage_bps,'latency_ms':args.latency_ms,
           'warning':'Simulated fills only; no exchange order; daily Upstox OAuth renewal required'})
    engine=None
    contract=None
    last_orb_poll=None
    seen_old=False
    error_count=0
    print('PAPER ONLY',session_id,'journal',path,'- no broker orders',flush=True)
    try:
        while clock().astimezone(IST)<session_until:
            now=clock().astimezone(IST)
            if engine is None:
                if now.time()>=dt.time(15,10):break
                if now.time()<dt.time(9,35):
                    sleep(args.poll_seconds);continue
                if last_orb_poll and (now-last_orb_poll).total_seconds()<args.candle_poll_seconds:
                    sleep(args.poll_seconds);continue
                last_orb_poll=now
                try:
                    bars=api.candles(INDICES[args.market])
                    orb=orb_signal(bars,day,now)
                    if orb['status']!='TRIGGERED':
                        if orb['status']=='EXPIRED':break
                        sleep(args.poll_seconds);continue
                    age=(now-parse_time(orb['trigger_time'])).total_seconds()
                    if age<0:continue
                    if age>args.max_signal_age_seconds:
                        seen_old=True
                        write({'event':'MISSED_SIGNAL','timestamp':now.isoformat(),
                               'trigger_time':orb['trigger_time'],'age_seconds':round(age,2),
                               'reason':'SIGNAL_TOO_OLD_NO_BACKFILL'})
                        break
                    selector=getattr(args,'selector','atm')
                    if selector=='delta':
                        nearest=select_atm(records,args.market,orb['side'],float(orb['entry_price']),day)
                        chain=api.option_chain(INDICES[args.market],nearest['expiry'])
                        try:
                            contract=select_delta_contract(
                                records,chain,args.market,orb['side'],float(orb['entry_price']),
                                day,settings,lots=args.lots,stop_pct=args.stop_pct,
                                max_spread_pct=args.max_spread_pct,fee_profile=args.fee_profile,
                                delta_min=getattr(args,'delta_min',0.40),
                                delta_max=getattr(args,'delta_max',0.65),
                                target_delta=getattr(args,'target_delta',0.50))
                        except UpstoxError as exc:
                            write({'event':'CONTRACT_FILTER_BLOCKED','timestamp':clock().astimezone(IST).isoformat(),
                                   'reason':str(exc),'selector':'delta'})
                            break
                    else:
                        contract=select_atm(records,args.market,orb['side'],float(orb['entry_price']),day)
                    # Reject if selecting the option chain took too long after the index signal.
                    if (clock().astimezone(IST)-parse_time(orb['trigger_time'])).total_seconds()>args.max_signal_age_seconds:
                        seen_old=True
                        write({'event':'MISSED_SIGNAL','timestamp':clock().astimezone(IST).isoformat(),
                               'reason':'SIGNAL_STALE_AFTER_CHAIN_LOOKUP'})
                        break
                    qty=int(contract['lot_size'])*int(args.lots)
                    # No unknown-margin or price index sizing; PaperEngine checks premium and max stop loss.
                    engine=PaperEngine(contract['symbol'],qty,settings['capital_inr'],
                        settings['max_loss_per_trade_inr'],stop_pct=args.stop_pct,
                        target_pct=args.target_pct,max_spread_pct=args.max_spread_pct,
                        slippage_bps=args.slippage_bps,latency_ms=args.latency_ms,
                        max_allocation_fraction=settings['max_allocation_fraction'],
                        fee_profile=args.fee_profile)
                    write({'event':'INDEX_SIGNAL','timestamp':now.isoformat(),
                           'underlying_key':INDICES[args.market],'trigger_time':orb['trigger_time'],
                           'side':orb['side'],'underlying_close':orb['entry_price'],
                           'contract':contract,'quantity':qty})
                    print('CLOSED ORB SIGNAL',orb['side'],contract['symbol'],'qty',qty,flush=True)
                except (UpstoxError,ValueError) as exc:
                    write({'event':'MARKET_DATA_ERROR','timestamp':now.isoformat(),'message':str(exc)})
                    error_count+=1
                    if error_count>=3:break
                    sleep(args.poll_seconds);continue
            try:
                q=api.full_quote(contract['instrument_key'])
                now=clock().astimezone(IST)
                age=(now-q.timestamp).total_seconds()
                write({'event':'QUOTE_SNAPSHOT','timestamp':q.timestamp.isoformat(),
                       'captured_at':now.isoformat(),'symbol':contract['symbol'],
                       'bid':q.bid,'ask':q.ask,'bid_qty':q.bid_qty,'ask_qty':q.ask_qty,'last':q.last,
                       'depth_buy':q.bid_levels,'depth_sell':q.ask_levels,'age_seconds':round(age,2)})
                signal=not any(e['event']=='ENTRY_SIGNAL' for e in engine.events) and engine.position is None and engine.pending is None
                ev=engine.process(q,signal=signal,reason='FRESH_INDEX_5M_ORB',now=now,
                                  max_age_seconds=args.max_quote_age_seconds)
                if ev:
                    write(ev)
                    print(json.dumps(ev,ensure_ascii=False),flush=True)
                    if ev['event']=='PAPER_TRADE_CLOSED':break
                    if ev['event']=='ENTRY_REJECTED':break
                error_count=0
            except (UpstoxError,ValueError,KeyError) as exc:
                write({'event':'MARKET_DATA_ERROR','timestamp':now.isoformat(),'message':str(exc)})
                error_count+=1
                if error_count>=5:break
            sleep(args.poll_seconds)
    except KeyboardInterrupt:
        write({'event':'USER_STOP','timestamp':clock().isoformat()})
    state=engine.summary() if engine else {'closed_trades':0,'gross_pnl':0.0,'total_fees':0.0,
                                           'realized_net_pnl':0.0,'open_position':None}
    if engine and engine.position:
        write({'event':'UNRESOLVED_POSITION','timestamp':clock().isoformat(),
               'position':engine.position,
               'warning':'No fictitious exit; position is still open in the SIMULATOR. Inspect market and reconcile.'})
    write({'event':'SESSION_SUMMARY','timestamp':clock().isoformat(), 'summary':state,
           'status':'MISSED_SIGNAL' if seen_old else ('UNRESOLVED' if state.get('open_position') else 'CLOSED_OR_NO_TRADE')})
    print(json.dumps({'session':session_id,'journal':str(path),'summary':state},indent=2),flush=True)
    return 0
