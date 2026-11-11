"""Create DEMONSTRATION journals from synthetic, invented quote paths only."""
import datetime as dt
from pathlib import Path
from .core import IST
from .paper_sim import PaperEngine, Quote, journal_write


def create_demo(directory='trader/demo_forward'):
    base=Path(directory);base.mkdir(parents=True,exist_ok=True)
    out=[]
    day=dt.date(2026,11,11)
    scenarios=[('NIFTY','NFO:DEMO_NIFTY_CE',[100,100.2,103,132,131.5],'SYNTHETIC_PROFIT'),
               ('SENSEX','BFO:DEMO_SENSEX_PE',[100,100.2,95,78,76],'SYNTHETIC_LOSS')]
    for market,symbol,pxs,tag in scenarios:
        path=base/(day.isoformat()+'_'+market+'_SYNTHETIC.jsonl')
        if path.exists():path.unlink()
        engine=PaperEngine(symbol,20,100000,500,fee_profile='UPSTOX',slippage_bps=5,latency_ms=500)
        def log(r):journal_write(path,{'mode':'DEMO_SYNTHETIC_NO_REAL_PRICES',
                                        'session':day.isoformat()+'_'+market+'_SYNTHETIC',
                                        'market':market,'source':'INVENTED_EXAMPLE_QUOTES',**r})
        log({'event':'SESSION_START','timestamp':dt.datetime(2026,11,11,9,35,tzinfo=IST).isoformat(),
             'warning':'Synthetic prices. Do not infer strategy profitability.'})
        ticks=[(35,0),(35,2),(36,0),(38,0),(38,2)]
        for i,((minute,sec),mid) in enumerate(zip(ticks,pxs)):
            q=Quote(dt.datetime(2026,11,11,9,minute,sec,tzinfo=IST),mid-0.2,mid+0.2,500,500,mid)
            log({'event':'QUOTE_SNAPSHOT','timestamp':q.timestamp.isoformat(), 'bid':q.bid,
                 'ask':q.ask,'last':q.last,'bid_qty':q.bid_qty,'ask_qty':q.ask_qty})
            ev=engine.process(q,signal=(i==0))
            if ev:log(ev)
        summary=engine.summary()
        log({'event':'SESSION_SUMMARY','timestamp':dt.datetime(2026,11,11,9,40,tzinfo=IST).isoformat(),
             'summary':summary,'warning':'Invented price paths, NOT real market results'})
        out.append({'file':str(path),'market':market,'closed_trades':summary['closed_trades'],
                    'net_pnl':summary['realized_net_pnl'],'scenario':tag})
    return out
