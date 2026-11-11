"""Summary of actual recorded *simulated* fills, NOT broker contract notes."""
import datetime as dt
import json
from pathlib import Path
from .paper_sim import money


def summary_from_folder(directory,monthly_fixed_cost=500.0, assumed_trading_days=21):
    if monthly_fixed_cost<0 or assumed_trading_days<1:
        raise ValueError('Bad fixed-cost assumptions')
    paths=sorted(Path(directory).glob('*.jsonl'))
    trades=[];sessions=0;open_runs=0
    for path in paths:
        rows=[]
        with path.open('r',encoding='utf-8') as f:
            for line in f:
                try: rows.append(json.loads(line))
                except json.JSONDecodeError: continue
        if not rows:continue
        sessions+=1
        closed=[r for r in rows if r.get('event')=='PAPER_TRADE_CLOSED']
        trades.extend(closed)
        if any(r.get('event')=='PAPER_BUY_FILLED' for r in rows) and not closed:
            open_runs+=1
    trades.sort(key=lambda x:x['timestamp'])
    pnl=[float(t['net_pnl']) for t in trades]
    fees=sum(float(t['fees']['total']) for t in trades)
    wins=[x for x in pnl if x>0]
    losses=[x for x in pnl if x<=0]
    days=sorted({dt.datetime.fromisoformat(t['timestamp']).date().isoformat() for t in trades})
    peak=0;cum=0;max_dd=0
    for value in pnl:
        cum+=value;peak=max(peak,cum);max_dd=min(max_dd,cum-peak)
    gross_prof=sum(max(0,x) for x in pnl)
    gross_loss=-sum(min(0,x) for x in pnl)
    fixed=monthly_fixed_cost/assumed_trading_days*len(days)
    return {'mode':'FORWARD_PAPER_ONLY_NOT_BROKER_FILLS','files':len(paths),'sessions':sessions,
            'closed_trades':len(trades),'open_unresolved_sessions':open_runs,
            'trading_days_with_closed_trades':len(days),'win_rate_pct':round(100*len(wins)/len(pnl),2) if pnl else None,
            'wins':len(wins),'losses_or_breakeven':len(losses),
            'gross_trading_pnl_before_fees':money(sum(t['gross_pnl'] for t in trades)),
            'fees_and_taxes':money(fees),'net_trading_pnl_after_fees':money(sum(pnl)),
            'estimated_data_and_fixed_cost':money(fixed),
            'estimated_net_after_fixed_cost':money(sum(pnl)-fixed),
            'cost_assumption':f'INR {monthly_fixed_cost}/month divided by {assumed_trading_days} trading days, applied only to days with closed trades',
            'average_net_trade':money(sum(pnl)/len(pnl)) if pnl else None,
            'profit_factor':round(gross_prof/gross_loss,3) if gross_loss>0 else None,
            'max_closed_trade_drawdown':money(-max_dd),
            'notes':['No mark-to-market equity drawdown for open positions',
                     'Closed-trade net P&L is based on SIMULATED, not confirmed, fills',
                     'Days with no trading are not charged the estimated fixed cost by this report',
                     'Broker contract-note fees and exchange fill quality may differ']}
