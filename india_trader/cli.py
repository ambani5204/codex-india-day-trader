"""CLI invoked by all eleven Codex skill folders.

No live orders can be submitted through this module.
"""
import argparse
import csv
import time
import datetime as dt
import json
import os
import secrets
import sys
from pathlib import Path
from .core import IST, backtest, exit_plan, is_index, monte_carlo, orb_signal, parse_time, read_bars, risk_check, size_position
from .feeds import headlines,financial_report,insider_summary
from .kite import KiteReader,KiteError,find_instrument,save_master
from .paper_sim import PaperEngine, option_fees, breakeven_sell, replay_csv, export_quote_snapshots

BASE=Path.cwd()

def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def config():
    p=Path('trader/config.json')
    return read_json(p if p.exists() else 'trader/config.example.json')

def paper_settings_partitioned(settings, partitions=1):
    """Isolate paper capital/risk for independent simultaneous market workers."""
    partitions=int(partitions)
    if partitions not in (1,2):
        raise ValueError('PAPER_MARKET_PARTITIONS must be 1 or 2')
    c=dict(settings)
    if partitions==2:
        for key in ('capital_inr','max_loss_per_trade_inr','max_daily_loss_inr'):
            c[key]=float(c[key])/2
        c['max_trades_per_day']=max(1,int(c['max_trades_per_day'])//2)
    c['_paper_market_partitions']=partitions
    return c

def dump(result): print(json.dumps(result,indent=2,ensure_ascii=False))

def bars_for(args):
    if args.csv:return read_bars(args.csv)
    c=config(); inst=find_instrument(c['instrument_cache'],args.symbol)
    return KiteReader().candles(inst['instrument_token'],args.date)

def add_bars_options(p):
    p.add_argument('--symbol',default='NSE:NIFTY 50',help='e.g. NSE:NIFTY 50, BSE:SENSEX or NSE:RELIANCE')
    p.add_argument('--date',default=dt.datetime.now(IST).date().isoformat())
    p.add_argument('--csv',help='offline CSV columns date,open,high,low,close,volume')
    p.add_argument('--as-of',help='IST timestamp; only bars fully closed before this time are processed')


def main(argv=None):
    p=argparse.ArgumentParser(prog='python tools/india.py',description='Indian market Codex trading tools; paper only')
    sub=p.add_subparsers(dest='cmd',required=True)
    inst=sub.add_parser('instruments');inst.add_argument('action',choices=['sync','resolve']);inst.add_argument('--symbol',default='NSE:NIFTY 50')
    hist=sub.add_parser('export-history');hist.add_argument('--symbol',required=True);hist.add_argument('--from-date',required=True);hist.add_argument('--to-date',required=True);hist.add_argument('--out',required=True)
    for cmd in ('scan','entry'):
        add_bars_options(sub.add_parser(cmd))
    ep=sub.add_parser('exit');ep.add_argument('--signal',default='trader/signal.json');ep.add_argument('--stop',choices=['mid','opposite'],default='mid');ep.add_argument('--rr',type=float,default=1.5)
    bt=sub.add_parser('timemachine');bt.add_argument('--csv',required=True);bt.add_argument('--iterations',type=int,default=10000);bt.add_argument('--seed',type=int,default=19)
    mp=sub.add_parser('manual-plan');mp.add_argument('--symbol',required=True);mp.add_argument('--side',choices=['BUY','SELL'],default='BUY');mp.add_argument('--entry',type=float,required=True);mp.add_argument('--stop',type=float,required=True);mp.add_argument('--target',type=float,required=True)
    sz=sub.add_parser('budget');sz.add_argument('--plan',default='trader/plan.json');sz.add_argument('--symbol',help='tradable EXCHANGE:TRADINGSYMBOL; omit to use plan symbol');sz.add_argument('--lot-size',type=int,default=None)
    rk=sub.add_parser('risk');rk.add_argument('--order',default='trader/orders.json');rk.add_argument('--daily-pnl',type=float,default=0);rk.add_argument('--trades-today',type=int,default=0)
    bk=sub.add_parser('broker');bk.add_argument('action',choices=['ticket','paper','live']);bk.add_argument('--order',default='trader/orders.json')
    al=sub.add_parser('alerts');al.add_argument('action',choices=['add','check','list']);al.add_argument('--symbol');al.add_argument('--above',type=float);al.add_argument('--below',type=float);al.add_argument('--ltp',type=float);al.add_argument('--from-plan',action='store_true')
    nw=sub.add_parser('news');nw.add_argument('--query',required=True);nw.add_argument('--limit',type=int,default=10)
    an=sub.add_parser('analyst');an.add_argument('--csv',required=True)
    ins=sub.add_parser('insiders');ins.add_argument('--csv',required=True)
    pc=sub.add_parser('paper-cost',help='Brokerage, STT, GST, exchange, SEBI, stamp: options buy then sell')
    pc.add_argument('--exchange',choices=['NFO','BFO'],required=True)
    pc.add_argument('--fee-profile',choices=['ZERODHA','UPSTOX'],default='ZERODHA')
    pc.add_argument('--buy',type=float,required=True);pc.add_argument('--sell',type=float,required=True)
    pc.add_argument('--qty',type=int,required=True)
    pr=sub.add_parser('paper-replay',help='Realistic quote-depth replay; synthetic test CSV is NOT live data')
    pr.add_argument('--quotes-csv',required=True);pr.add_argument('--contract',required=True)
    pr.add_argument('--qty',type=int,required=True);pr.add_argument('--signal-time')
    pr.add_argument('--fee-profile',choices=['ZERODHA','UPSTOX'],default='ZERODHA')
    pr.add_argument('--stop-pct',type=float,default=15);pr.add_argument('--target-pct',type=float,default=30)
    pr.add_argument('--max-spread-pct',type=float,default=2)
    pr.add_argument('--slippage-bps',type=float,default=5);pr.add_argument('--latency-ms',type=int,default=750)
    pr.add_argument('--journal',help='Optional JSONL record file')
    pl=sub.add_parser('paper-live',help='Poll Kite FULL quotes and simulate INTRADAY options; NO orders')
    pl.add_argument('--contract',help='Actual unexpired NFO/BFO option symbol from today Kite master; omit with --auto-atm')
    pl.add_argument('--auto-atm',action='store_true',help='At fresh index ORB trigger automatically select nearest expiry, nearest strike ATM call/put from current Kite master')
    pl.add_argument('--index',choices=['NSE:NIFTY 50','BSE:SENSEX'],help='Require new closed 5-min ORB trigger (CE for up, PE for down); omit for immediate manual paper entry')
    pl.add_argument('--lots',type=int,default=1)
    pl.add_argument('--stop-pct',type=float,default=15);pl.add_argument('--target-pct',type=float,default=30)
    pl.add_argument('--max-spread-pct',type=float,default=2)
    pl.add_argument('--slippage-bps',type=float,default=5);pl.add_argument('--latency-ms',type=int,default=750)
    pl.add_argument('--max-quote-age-seconds',type=float,default=15)
    pl.add_argument('--poll-seconds',type=float,default=3)
    pl.add_argument('--max-minutes',type=float,default=375)
    qe=sub.add_parser('paper-export-quotes',help='Export recorded live quote snapshots to verifiable replay CSV')
    qe.add_argument('--journal',required=True);qe.add_argument('--out',required=True)
    rpt=sub.add_parser('paper-report',help='Aggregate net profits after fees from JSONL simulated sessions')
    rpt.add_argument('--directory',default='trader/paper_forward')
    rpt.add_argument('--fixed-cost-per-month',type=float,default=500)
    rpt.add_argument('--assumed-trading-days',type=int,default=21)
    us=sub.add_parser('upstox-sync',help='Download PUBLIC BOD JSON instrument master; no credentials required')
    us.add_argument('--out',default='trader/upstox_instruments.json')
    pu=sub.add_parser('paper-upstox',help='Live Upstox V3 REST snapshot paper simulation; never sends orders')
    pu.add_argument('--market',choices=['NIFTY','SENSEX'],required=True)
    pu.add_argument('--selector',choices=['delta','atm'],default='delta',
                    help='Delta/premium option-chain filter; ATM only for testing backwards compatibility')
    pu.add_argument('--delta-min',type=float,default=0.40)
    pu.add_argument('--delta-max',type=float,default=0.65)
    pu.add_argument('--target-delta',type=float,default=0.50)
    pu.add_argument('--lots',type=int,default=1)
    pu.add_argument('--master',default='trader/upstox_instruments.json')
    pu.add_argument('--directory',default='trader/paper_upstox')
    pu.add_argument('--fee-profile',choices=['ZERODHA','UPSTOX'],default='UPSTOX')
    pu.add_argument('--stop-pct',type=float,default=15)
    pu.add_argument('--target-pct',type=float,default=30)
    pu.add_argument('--max-spread-pct',type=float,default=2)
    pu.add_argument('--slippage-bps',type=float,default=5)
    pu.add_argument('--latency-ms',type=int,default=750)
    pu.add_argument('--poll-seconds',type=float,default=5)
    pu.add_argument('--candle-poll-seconds',type=float,default=30)
    pu.add_argument('--max-quote-age-seconds',type=float,default=15)
    pu.add_argument('--max-signal-age-seconds',type=float,default=90)
    pu.add_argument('--max-minutes',type=float,default=390)
    store=sub.add_parser('db-sync',help='Archive paper journals into durable SQLite database')
    store.add_argument('--directory',default='trader/paper_upstox')
    store.add_argument('--database',default='trader/paper.sqlite3')
    sums=sub.add_parser('db-report',help='Daily or monthly net paper result from SQLite')
    sums.add_argument('--period',choices=['day','month'],default='day')
    sums.add_argument('--date',help='YYYY-MM-DD for day, YYYY-MM for month')
    sums.add_argument('--database',default='trader/paper.sqlite3')
    btidx=sub.add_parser('backtest-index-signals',
        help='Historical index-only 5m replay using SAME multi-signal strategy; NO options profit figures')
    btidx.add_argument('--from-date',required=True,help='YYYY-MM-DD, inclusive')
    btidx.add_argument('--to-date',required=True,help='YYYY-MM-DD, inclusive')
    btidx.add_argument('--market',choices=['AUTO','NIFTY','SENSEX','BOTH'],default='AUTO')
    btidx.add_argument('--cache-dir',default='trader/backtest_cache')
    btidx.add_argument('--out',default='trader/backtests/index_signals.json')
    idxbt=sub.add_parser('backtest-index-intraday',
        help='Backtest same advanced signals/stops as hypothetical index CHART POINTS only; no put/call, no traded index')
    idxbt.add_argument('--from-date',required=True,help='YYYY-MM-DD inclusive')
    idxbt.add_argument('--to-date',required=True,help='YYYY-MM-DD inclusive')
    idxbt.add_argument('--market',choices=['AUTO','NIFTY','SENSEX','BOTH'],default='AUTO')
    idxbt.add_argument('--cache-dir',default='trader/backtest_cache')
    idxbt.add_argument('--out',default='trader/backtests/index_intraday.json')
    idxbt.add_argument('--slippage-points',type=float,default=0.0,
                       help='Hypothetical adverse index points per entry and exit; default zero')
    diag=sub.add_parser('paper-diagnose',help='Show exact local paper signal, stop, target and rejection reasons; read-only')
    diag.add_argument('--date',required=True,help='YYYY-MM-DD')
    diag.add_argument('--market',choices=['SENSEX','NIFTY'],required=True)
    diag.add_argument('--directory',default='trader/paper_upstox')
    adv=sub.add_parser('paper-advanced',help='EXPERIMENTAL all-session multi-signal, long options + hedged credit spreads; paper ONLY')
    adv.add_argument('--market',choices=['NIFTY','SENSEX'],required=True)
    adv.add_argument('--master',default='trader/upstox_instruments.json')
    adv.add_argument('--directory',default='trader/paper_upstox')
    adv.add_argument('--poll-seconds',type=float,default=30)
    adv.add_argument('--cooldown-minutes',type=float,default=15)
    adv.add_argument('--max-quote-age-seconds',type=float,default=15)
    adv.add_argument('--credit-iv-threshold',type=float,default=18)
    demo=sub.add_parser('demo-generate',help='Generate EXPLICITLY SYNTHETIC winning and losing paper sessions')
    demo.add_argument('--directory',default='trader/demo_forward')
    dash=sub.add_parser('dashboard',help='Serve mobile paper-only dashboard; demo by default')
    dash.add_argument('--mode',choices=['demo','upstox'],default='demo')
    dash.add_argument('--directory',help='Journal directory; defaults based on mode')
    dash.add_argument('--host',default='127.0.0.1')
    dash.add_argument('--port',type=int,default=8080)
    dash.add_argument('--monthly-fixed-cost',type=float,default=0)
    args=p.parse_args(argv)
    try:
        return dispatch(args)
    except (ValueError,KeyError,OSError,KiteError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);return 2


def dispatch(a):
    if a.cmd=='db-sync':
        from .storage import sync_journals
        dump(sync_journals(a.directory,a.database));return 0
    if a.cmd=='db-report':
        from .storage import period_report
        dump(period_report(a.period,a.date,a.database));return 0
    if a.cmd=='paper-diagnose':
        from .diagnostics import diagnose_paper_sessions
        dump(diagnose_paper_sessions(a.directory,a.date,a.market))
        return 0
    if a.cmd=='backtest-index-intraday':
        from .index_intraday_backtest import backtest_index_intraday
        result=backtest_index_intraday(
            a.from_date,a.to_date,a.market,cache_dir=a.cache_dir,
            out=a.out,slippage_points=a.slippage_points)
        dump({'kind':result['kind'],'from_date':result['from_date'],
              'to_date':result['to_date'],'markets':result['market_mode'],
              'candidate_signals':result['candidate_signals'],
              'complete_sessions':result['complete_sessions'],
              'excluded_sessions':result['excluded_sessions'],
              'excluded_by_reason':result['excluded_by_reason'],
              'overall':result['overall'],
              'by_strategy':result['by_strategy'],
              'by_market':result['by_market'],
              'rejected_signals':result['rejected_signals'],
              'options_net_pnl_inr':None,
              'results_path':a.out,'warning':result['warning']})
        return 0
    if a.cmd=='backtest-index-signals':
        from .historical_backtest import annual_signal_backtest
        result=annual_signal_backtest(a.from_date,a.to_date,a.market,
            cache_dir=a.cache_dir,out=a.out)
        dump({'kind':result['kind'],'from_date':result['from_date'],
              'to_date':result['to_date'],'markets':result['market_mode'],
              'days_analyzed':result['days_analyzed'],
              'days_with_complete_bars':result['days_with_complete_bars'],
              'missing_or_incomplete_days':result['missing_or_incomplete_days'],
              'candidate_signals':result['candidate_signals'],
              'by_strategy':result['by_strategy'],
              'options_net_pnl':None,'results_path':a.out,
              'warning':result['warning']})
        return 0
    if a.cmd=='upstox-sync':
        from .upstox import sync_instruments
        dump(sync_instruments(a.out));return 0
    if a.cmd=='demo-generate':
        from .demo import create_demo
        dump({'mode':'SYNTHETIC_DEMONSTRATION','sessions':create_demo(a.directory)});return 0
    if a.cmd=='dashboard':
        from .dashboard import serve_dashboard
        folder=a.directory or ('trader/demo_forward' if a.mode=='demo' else 'trader/paper_upstox')
        if a.mode=='demo' and not list(Path(folder).glob('*.jsonl')):
            from .demo import create_demo
            create_demo(folder)
        serve_dashboard(a.host,a.port,folder,a.mode,a.monthly_fixed_cost)
        return 0
    cfg=config()
    if a.cmd=='paper-advanced':
        from .advanced_forward import run_advanced
        cfg=paper_settings_partitioned(cfg,os.environ.get('PAPER_MARKET_PARTITIONS','1'))
        return run_advanced(a,cfg)
    if a.cmd=='paper-upstox':
        from .upstox_forward import run_upstox
        cfg=paper_settings_partitioned(cfg,os.environ.get('PAPER_MARKET_PARTITIONS','1'))
        return run_upstox(a,cfg)
    if a.cmd=='paper-cost':
        fees=option_fees(a.buy,a.sell,a.qty,a.exchange,a.fee_profile)
        gross=(a.sell-a.buy)*a.qty
        dump({'market':'INDIA_INDEX_OPTION_LONG_INTRADAY','exchange':a.exchange,
              'buy':a.buy,'sell':a.sell,'quantity':a.qty,'broker_profile':a.fee_profile,
              'gross_pnl':round(gross,2),'fees':fees,'net_pnl':round(gross-fees['total'],2),
              'breakeven_sell':breakeven_sell(a.buy,a.qty,a.exchange,a.fee_profile),
              'warning':'Cost estimate, not exact broker contract note. Expiry exercise, DP, tax and subscription excluded.'})
        return 0
    if a.cmd=='paper-replay':
        if a.qty<1:raise ValueError('Quantity must be positive')
        e=PaperEngine(a.contract,a.qty,cfg['capital_inr'],cfg['max_loss_per_trade_inr'],
                      stop_pct=a.stop_pct,target_pct=a.target_pct,
                      max_spread_pct=a.max_spread_pct,slippage_bps=a.slippage_bps,
                      latency_ms=a.latency_ms,max_allocation_fraction=cfg['max_allocation_fraction'],
                      fee_profile=a.fee_profile)
        result=replay_csv(a.quotes_csv,e,a.signal_time,a.journal)
        result['quotes_file']=a.quotes_csv
        result['data_source']='USER_SUPPLIED_REPLAY_QUOTES'
        dump(result)
        return 0
    if a.cmd=='paper-live':
        from .live_forward import run_live
        return run_live(a,cfg)
    if a.cmd=='paper-export-quotes':
        n=export_quote_snapshots(a.journal,a.out)
        dump({'exported_quotes':n,'path':a.out,'warning':'CSV exports only top-of-book, not all recorded depth levels; real trading fills are NOT guaranteed'})
        return 0
    if a.cmd=='paper-report':
        from .report import summary_from_folder
        dump(summary_from_folder(a.directory,a.fixed_cost_per_month,a.assumed_trading_days))
        return 0
    if a.cmd=='instruments':
        if a.action=='sync':
            n=save_master(KiteReader(),cfg['instrument_cache']);dump({'status':'SYNCED','rows':n,'path':cfg['instrument_cache']})
        else:
            inst=find_instrument(cfg['instrument_cache'],a.symbol)
            dump({'symbol':a.symbol,'instrument_token':inst['instrument_token'],'lot_size':inst['lot_size'],
                  'expiry':inst['expiry'],'segment':inst['segment'],'is_index':is_index(a.symbol,inst)})
        return 0
    if a.cmd=='export-history':
        date1=dt.date.fromisoformat(a.from_date);date2=dt.date.fromisoformat(a.to_date)
        if date2<date1 or (date2-date1).days>365:raise ValueError('Date range must be 0-365 calendar days')
        instrument=find_instrument(cfg['instrument_cache'],a.symbol)
        token=instrument['instrument_token'];kite=KiteReader()
        bars=[];day=date1
        while day<=date2:
            end=min(day+dt.timedelta(days=49),date2)
            bars.extend(kite.candles_range(token,day.isoformat()+' 00:00:00',end.isoformat()+' 23:59:59'))
            day=end+dt.timedelta(days=1)
            if day<=date2:time.sleep(.4)
        path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['date','open','high','low','close','volume'])
            writer.writerows([[b.time.isoformat(),b.open,b.high,b.low,b.close,b.volume] for b in sorted(bars,key=lambda x:x.time)])
        dump({'symbol':a.symbol,'candles':len(bars),'path':str(path),'data_mode':'KITE_HISTORICAL_5MIN','from':str(date1),'to':str(date2)})
        return 0
    if a.cmd in ('scan','entry'):
        bars=bars_for(a)
        asof=a.as_of or (dt.datetime.now(IST).isoformat() if a.date==dt.datetime.now(IST).date().isoformat() else a.date+'T15:30:00+05:30')
        result=orb_signal(bars,a.date,asof)
        result['symbol']=a.symbol;result['is_index']=is_index(a.symbol)
        result['data_mode']='OFFLINE_CSV' if a.csv else 'ZERODHA_KITE_HISTORICAL'
        write_json('trader/signal.json',result)
        dump(result)
        return 0
    if a.cmd=='exit':
        plan=exit_plan(read_json(a.signal),a.stop,a.rr)
        write_json('trader/plan.json',plan);dump(plan);return 0
    if a.cmd=='timemachine':
        bars=read_bars(a.csv);back=backtest(bars)
        if len({b.time.date() for b in bars})>=20:
            back['bootstrap']=monte_carlo(bars,a.iterations,a.seed)
        else:back['bootstrap']={'status':'SKIPPED','reason':'Need 20 or more trading sessions'}
        write_json('trader/backtest.json',back);dump(back);return 0
    if a.cmd=='manual-plan':
        if is_index(a.symbol):raise ValueError('Not a tradable instrument: '+a.symbol)
        if a.entry<=0 or a.stop<=0 or a.target<=0:raise ValueError('Prices must be positive')
        risk=(a.entry-a.stop) if a.side=='BUY' else (a.stop-a.entry)
        reward=(a.target-a.entry) if a.side=='BUY' else (a.entry-a.target)
        if risk<=0 or reward<=0:raise ValueError('Stop and target must be correctly oriented for chosen side')
        plan={'symbol':a.symbol,'side':a.side,'entry_price':a.entry,'stop_price':a.stop,'target_price':a.target,
              'risk_per_unit':risk,'reward_risk':round(reward/risk,3),'source':'MANUALLY_ENTERED_ACTUAL_CONTRACT_PRICE',
              'signal_timestamp':dt.datetime.now(IST).isoformat(),'flat_by':'15:20 IST'}
        write_json('trader/plan.json',plan);dump(plan);return 0
    if a.cmd=='budget':
        plan=read_json(a.plan)
        sym=a.symbol or plan.get('symbol')
        if not sym:raise ValueError('Specify --symbol with a tradable instrument')
        if is_index(sym):raise ValueError('Cannot trade an index; specify a tradable NSE/BSE equity or NFO/BFO contract')
        if plan.get('symbol') and plan['symbol']!=sym:
            raise ValueError('Plan instrument differs from order instrument. Never size an option using the underlying index entry/stop; use manual-plan for actual contract prices.')
        instrument=None
        if Path(cfg['instrument_cache']).exists():
            instrument=find_instrument(cfg['instrument_cache'],sym)
        lot_size=a.lot_size or (int(instrument['lot_size']) if instrument else 1)
        if sym.split(':')[0] in ('NFO','BFO') and not instrument:
            raise ValueError('Derivative sizing requires a fresh synced instrument master (lot size and expiry)')
        if sym.split(':')[0] in ('NFO','BFO') and not cfg.get('allow_derivatives',False):
            raise ValueError('Derivatives are disabled in config')
        plan['symbol']=sym
        order=size_position(plan,cfg['capital_inr'],cfg['max_loss_per_trade_inr'],cfg['max_allocation_fraction'],lot_size,cfg['allow_short'])
        order['product']='NRML' if sym.split(':')[0] in {'NFO','BFO'} else order['product']
        order['id']='PAPER-'+secrets.token_hex(4).upper()
        order['data_source']='USER_CONFIRMED_INSTRUMENT'
        write_json('trader/orders.json',order);dump(order);return 0
    if a.cmd=='risk':
        order=read_json(a.order)
        inst=None
        if Path(cfg['instrument_cache']).exists():inst=find_instrument(cfg['instrument_cache'],order['symbol'])
        result=risk_check(order,cfg,inst,a.daily_pnl,a.trades_today)
        write_json('trader/risk.json',result);dump(result)
        return 0 if result['status']=='PASS' else 3
    if a.cmd=='broker':
        order=read_json(a.order)
        if a.action=='live':
            print('BLOCKED: this version deliberately contains NO live order submission. Use Zerodha UI after separate manual verification.');return 4
        if a.action=='ticket':
            dump({'mode':'PAPER_ONLY','order':order,'warning':'No protective stop order is placed; not a real order.'});return 0
        inst=find_instrument(cfg['instrument_cache'],order['symbol']) if Path(cfg['instrument_cache']).exists() else None
        check=risk_check(order,cfg,inst)
        previous=Path('trader/risk.json')
        if not previous.exists():raise ValueError('Run risk and review PASS before paper-recording an order')
        signed=read_json(previous)
        if signed.get('status')!='PASS' or signed.get('order')!=order:
            raise ValueError('No matching PASS result for this exact order. Rerun risk.')
        if check['status']!='PASS':
            dump(check);return 3
        journal=Path('trader/paper_orders.jsonl');journal.parent.mkdir(parents=True,exist_ok=True)
        if journal.exists():
            for line in journal.read_text().splitlines():
                if json.loads(line)['id']==order['id']:raise ValueError('Duplicate paper order ID')
        record={**order,'status':'PAPER_RECORDED_NOT_FILLED','submitted_at':dt.datetime.now(IST).isoformat()}
        with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
        dump(record);return 0
    if a.cmd=='alerts':
        path=Path('trader/alerts.json')
        alerts=read_json(path) if path.exists() else []
        if a.action=='list':dump(alerts);return 0
        if a.action=='add':
            if a.from_plan:
                plan=read_json('trader/plan.json');sym=plan['symbol']
                to_add=[{'symbol':sym,'kind':'STOP','value':plan['stop_price'],'side':plan['side'],'fired':False},
                        {'symbol':sym,'kind':'TARGET','value':plan['target_price'],'side':plan['side'],'fired':False}]
            else:
                if not a.symbol or (a.above is None and a.below is None):raise ValueError('Provide --symbol and --above or --below')
                to_add=[{'symbol':a.symbol,'kind':'ABOVE' if a.above is not None else 'BELOW',
                         'value':a.above if a.above is not None else a.below,'fired':False}]
            alerts.extend(to_add);write_json(path,alerts);dump(to_add);return 0
        if a.action=='check':
            if not a.symbol:raise ValueError('Provide --symbol')
            price=a.ltp
            if price is None:
                quotes=KiteReader().quotes([a.symbol]); price=quotes[a.symbol]['last_price']
            fired=[]
            for alert in alerts:
                if alert['symbol']!=a.symbol or alert.get('fired'):continue
                above=price>=alert['value']; below=price<=alert['value']
                kind=alert['kind'];side=alert.get('side')
                trigger=(kind=='ABOVE' and above) or (kind=='BELOW' and below) or (kind=='STOP' and (below if side=='BUY' else above)) or (kind=='TARGET' and (above if side=='BUY' else below))
                if trigger:alert['fired']=True;alert['triggered_at']=dt.datetime.now(IST).isoformat();fired.append(alert)
            write_json(path,alerts);dump({'symbol':a.symbol,'last_price':price,'triggered':fired,'mode':'ON_DEMAND_ONLY'});return 0
    if a.cmd=='news':dump({'query':a.query,'headlines':headlines(a.query,a.limit),'note':'Public syndicated RSS; verify stories with original publishers.'});return 0
    if a.cmd=='analyst':dump(financial_report(a.csv));return 0
    if a.cmd=='insiders':dump(insider_summary(a.csv));return 0
    raise ValueError('Unknown command')
