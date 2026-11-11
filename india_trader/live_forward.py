"""Kite Connect read-only quote polling for index-option forward PAPER trading.

No Kite post/put/delete transport. Never places orders, never logs secrets.
"""
import datetime as dt
import csv
import json
import time
from pathlib import Path
from .core import IST, orb_signal, parse_time
from .kite import KiteReader, find_instrument
from .paper_sim import PaperEngine, Quote, journal_write
from .report import summary_from_folder


def select_atm_contract(master, index_symbol, signal_side, underlying_price, today):
    """Deterministic nearest-expiry ATM option selection at a CLOSED index signal.

    Not a recommendation, and selected contract may have unusable bid/ask depth.
    """
    mapping={'NSE:NIFTY 50':('NFO','NIFTY'), 'BSE:SENSEX':('BFO','SENSEX')}
    if index_symbol not in mapping or signal_side not in {'BUY','SELL'}:
        raise ValueError('Supported ATM signals: NIFTY 50 and SENSEX BUY/SELL only')
    exchange,name=mapping[index_symbol]
    contract_type='CE' if signal_side=='BUY' else 'PE'
    candidates=[]
    with Path(master).open('r',newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('exchange')!=exchange or r.get('name','').upper()!=name or r.get('instrument_type','').upper()!=contract_type:
                continue
            try:
                expiry=dt.date.fromisoformat(r.get('expiry',''))
                strike=float(r.get('strike',0));lot=int(float(r.get('lot_size','0')))
            except (ValueError,TypeError):continue
            if expiry<=today or strike<=0 or lot<1:continue
            candidates.append((expiry,abs(strike-float(underlying_price)),strike,r['tradingsymbol'],r))
    if not candidates:raise ValueError('No unexpired listed ATM option found in current master')
    _,_,_,sym,inst=min(candidates,key=lambda x:(x[0],x[1],x[2],x[3]))
    return exchange+':'+sym,inst


def run_auto_atm(args,settings):
    if args.contract or not args.index:
        raise ValueError('With --auto-atm specify --index, omit --contract')
    now=dt.datetime.now(IST)
    if now.weekday()>=5 or not dt.time(9,15)<=now.time()<dt.time(15,10):
        raise ValueError('Auto-ATM mode requires a weekday, before 15:10 IST')
    cache=Path(settings['instrument_cache'])
    if not cache.exists() or dt.datetime.fromtimestamp(cache.stat().st_mtime,IST).date()!=now.date():
        raise ValueError('Run instruments sync today before auto-ATM mode')
    underlying=find_instrument(str(cache),args.index)
    kite=KiteReader()
    print('READ-ONLY AUTO ATM: waiting for NEW CLOSED 5-minute ORB signal on',args.index,flush=True)
    until=now+dt.timedelta(minutes=args.max_minutes)
    try:
        while dt.datetime.now(IST)<until:
            now=dt.datetime.now(IST)
            if now.time()>=dt.time(15,10):break
            if now.time()<dt.time(9,35):
                time.sleep(min(15,max(1,args.poll_seconds)));continue
            bars=kite.candles(underlying['instrument_token'],now.date().isoformat())
            orb=orb_signal(bars,now.date(),now)
            if orb['status']=='TRIGGERED':
                age=(now-parse_time(orb['trigger_time'])).total_seconds()
                if age>90:
                    print('Previously triggered ORB too old for valid forward entry. Ending with no trade.',flush=True)
                    return 0
                if age>=0:
                    contract,inst=select_atm_contract(str(cache),args.index,orb['side'],orb['entry_price'],now.date())
                    print(json.dumps({'auto_selection':'NEAREST_EXPIRY_NEAREST_STRIKE_ATM',
                                      'underlying':args.index,'signal_side':orb['side'],
                                      'signal_timestamp':orb['trigger_time'],'underlying_close':orb['entry_price'],
                                      'contract':contract,'contract_expiry':inst['expiry'],
                                      'lot_size':inst['lot_size'],'warning':'Actual option quote depth still required'}),flush=True)
                    args.contract=contract;args.auto_atm=False;args.auto_atm_selected=True
                    return run_live(args,settings)
            time.sleep(max(3,args.poll_seconds))
    except KeyboardInterrupt:
        print('Stopped before signal; no paper trade placed.',flush=True)
    return 0


def run_live(args, settings):
    if args.auto_atm:return run_auto_atm(args,settings)
    contract=args.contract
    if not contract:raise ValueError("Supply --contract or use --auto-atm --index")
    exchange=contract.split(':',1)[0]
    if exchange not in {'NFO','BFO'} or not contract.endswith(('CE','PE')):
        raise ValueError('Select a valid NFO/BFO tradable option contract, e.g. an actual instrument from Kite master')
    if args.index:
        expected_exchange={'NSE:NIFTY 50':'NFO','BSE:SENSEX':'BFO'}
        if args.index not in expected_exchange:
            raise ValueError('ORB mode currently supports NSE:NIFTY 50 and BSE:SENSEX only')
        if exchange != expected_exchange[args.index]:
            raise ValueError('Underlying exchange does not match contract exchange')
    now=dt.datetime.now(IST)
    if now.weekday()>=5:
        raise ValueError('Not a weekday; no live forward paper session')
    if not (dt.time(9,15)<=now.time()<dt.time(15,20)):
        raise ValueError('Run between 09:15 and 15:20 IST only; no fake after-hours live fills')
    cache=Path(settings['instrument_cache'])
    if not cache.exists():raise ValueError('Run instruments sync first; Kite master required')
    # Master must have been regenerated for this India trading date.
    mtime=dt.datetime.fromtimestamp(cache.stat().st_mtime,IST).date()
    if mtime!=now.date():raise ValueError('Instrument master is not from today; sync before live paper trading')
    instrument=find_instrument(str(cache),contract)
    if instrument.get('instrument_type','').upper() not in {'CE','PE'}:
        raise ValueError('Selected instrument is not an option')
    expiry=instrument.get('expiry')
    if not expiry or dt.date.fromisoformat(expiry)<now.date():
        raise ValueError('Missing or expired contract expiry')
    lot=int(float(instrument['lot_size']))
    qty=lot*args.lots
    if lot<1 or args.lots<1:raise ValueError('Invalid lot size')
    if not settings.get('paper',True) or settings.get('allow_live_orders',False):
        raise ValueError('Safety policy requires paper=true, allow_live_orders=false')
    # Derivative permission remains analysis only. No API order endpoint exists.
    if not settings.get('allow_derivatives',False):
        raise ValueError('For options forward-paper analysis set allow_derivatives=true in private config; NO live orders supported')
    daily_dir=Path('trader/paper_forward')
    today_reports=[]
    for record_file in daily_dir.glob(now.strftime('%Y-%m-%d')+'_*.jsonl'):
        events=[]
        with record_file.open('r',encoding='utf-8') as f:
            for line in f:
                try:events.append(json.loads(line))
                except json.JSONDecodeError:pass
        if any(e.get('event')=='PAPER_BUY_FILLED' for e in events) and not any(e.get('event')=='PAPER_TRADE_CLOSED' for e in events):
            raise ValueError('Unresolved paper position in '+str(record_file)+'; do not double-count risk or pretend it closed')
        today_reports.extend(e for e in events if e.get('event')=='PAPER_TRADE_CLOSED')
    realized=sum(float(e['net_pnl']) for e in today_reports)
    if realized <= -float(settings['max_daily_loss_inr']):
        raise ValueError('Daily paper loss limit reached; blocked')
    if len(today_reports)>=int(settings['max_trades_per_day']):
        raise ValueError('Daily paper trade count reached; blocked')
    engine=PaperEngine(contract,qty,settings['capital_inr'],settings['max_loss_per_trade_inr'],
                       stop_pct=args.stop_pct,target_pct=args.target_pct,
                       max_spread_pct=args.max_spread_pct,slippage_bps=args.slippage_bps,
                       latency_ms=args.latency_ms,
                       max_allocation_fraction=settings['max_allocation_fraction'])
    kite=KiteReader()
    journal=Path('trader/paper_forward')/(now.strftime('%Y-%m-%d_%H%M%S')+'_'+contract.replace(':','_')+'.jsonl')
    if journal.exists():raise ValueError('Journal collision')
    journal_write(journal,{'event':'SESSION_START','mode':'READ_ONLY_LIVE_QUOTES_PAPER_EXECUTION',
                            'contract':contract,'index_signal':args.index,'timestamp':now.isoformat(),
                            'selection':'NEAREST_NONEXPIRING_ATM_FROM_FIRST_CLOSED_ORB' if getattr(args,'auto_atm_selected',False) else 'USER_SPECIFIED_CONTRACT',
                            'quantity':qty,'lot_size':lot,'stop_pct':args.stop_pct,'target_pct':args.target_pct,
                            'slippage_bps':args.slippage_bps,'latency_ms':args.latency_ms,
                            'fee_schedule':'2026-04-01','assumption':'not actual exchange fills'})
    print('PAPER ONLY: Kite read-only quotes. No broker orders. Journal:',journal,flush=True)
    first_signal=False
    last_orb_query=None
    session_end=now+dt.timedelta(minutes=args.max_minutes)
    last_print=None
    try:
        while dt.datetime.now(IST)<session_end:
            now=dt.datetime.now(IST)
            if now.time()>=dt.time(15,30):break
            try:
                quotes=kite.full_quotes([contract])
                data=quotes.get(contract)
                if not data:
                    print('QUOTE MISSING: no simulation fill',flush=True)
                    time.sleep(args.poll_seconds);continue
                q=Quote.from_kite(data)
                journal_write(journal, {'event':'QUOTE_SNAPSHOT','symbol':contract,
                                        'timestamp':q.timestamp.isoformat(),
                                        'captured_at':now.isoformat(),
                                        'bid':q.bid,'ask':q.ask,'bid_qty':q.bid_qty,'ask_qty':q.ask_qty,
                                        'last':q.last,'depth_buy':q.bid_levels,'depth_sell':q.ask_levels})
                signal=False
                if not first_signal and engine.position is None and engine.pending is None:
                    if args.index is None:
                        signal=True;first_signal=True
                    elif (now.time()>=dt.time(9,35) and
                          (last_orb_query is None or (now-last_orb_query).total_seconds()>=30)):
                        last_orb_query=now
                        source=find_instrument(str(cache),args.index)
                        bars=kite.candles(source['instrument_token'],now.date().isoformat())
                        orb=orb_signal(bars,now.date(),now)
                        if orb['status']=='TRIGGERED':
                            age=(now-parse_time(orb['trigger_time'])).total_seconds()
                            expected_type='CE' if orb['side']=='BUY' else 'PE'
                            if age<=90 and age>=0 and instrument['instrument_type'].upper()==expected_type:
                                signal=True;first_signal=True
                                print('New closed-bar ORB trigger:',orb['side'],orb['trigger_time'],flush=True)
                            elif age>90:
                                print('ORB trigger is old; do not backfill a fictitious historical entry',flush=True)
                                first_signal=True
                event=engine.process(q,signal=signal,reason='INDEX_ORB' if args.index else 'MANUAL_PAPER_START',
                                     now=now,max_age_seconds=args.max_quote_age_seconds)
                if event:
                    journal_write(journal,event)
                    print(json.dumps(event),flush=True)
                    if event['event']=='PAPER_TRADE_CLOSED':break
                if last_print is None or (now-last_print).total_seconds()>60:
                    last_print=now
                    print('QUOTE',now.isoformat(),contract,'bid',q.bid,'ask',q.ask,
                          'open',bool(engine.position),'no orders placed',flush=True)
            except (ValueError,KeyError,OSError) as exc:
                print('DATA / VALIDATION ISSUE: no fill on this cycle:',str(exc),flush=True)
            time.sleep(max(1.0,args.poll_seconds))
    except KeyboardInterrupt:
        print('Stopped by user. Open paper position, if any, is NOT silently closed.',flush=True)
    summary=engine.summary()
    summary['journal']=str(journal)
    summary['data_source']='ZERODHA_KITE_FULL_QUOTE_READ_ONLY'
    summary['risk_warning']='No connection to order system, live paper fills are estimates. No automatic cash brokerage exit.'
    journal_write(journal,{'event':'SESSION_SUMMARY','timestamp':dt.datetime.now(IST).isoformat(), 'summary':summary})
    print(json.dumps(summary,indent=2),flush=True)
    return 0
