"""Read-only diagnostics for Upstox paper journals.

The journal is the only source of truth: absent order events are not treated
as evidence that a specific stop or liquidity filter blocked an entry.
Never touch token files or broker APIs.
"""
from __future__ import annotations

from collections import Counter
import datetime as dt
import json
from pathlib import Path


def diagnose_paper_sessions(directory, day, market):
    day=dt.date.fromisoformat(day).isoformat()
    if market not in ('NIFTY','SENSEX'):
        raise ValueError('market must be NIFTY or SENSEX')
    files=sorted(Path(directory).glob(f'{day}_{market}_*.jsonl'))
    summary={'day':day,'market':market,'journal_files':len(files),
             'source':'LOCAL_PAPER_JOURNALS_NOT_REAL_ORDERS',
             'signals':0,'signals_by_strategy':{},'risk_plans':0,
             'credit_spread_opens':0,'long_option_fills':0,'closed_trades':0,
             'credit_structure_rejections':0,'long_fallback_attempts':0,
             'long_fallback_selections':0,'recent_structure_rejections':[],
             'net_realized_paper_pnl':0.,'pending_or_unresolved_sessions':0,
             'market_data_errors':0,'recent_market_data_errors':[],
             'rejections':[],'recent_risk_plans':[],
             'message':'No matching paper journal files' if not files else
                       'Events are simulated. No broker orders were placed.'}
    types=Counter()
    rejects=Counter()
    plans=[]
    errors=[]
    structures=[]
    unresolved=0
    pnl=0.0
    for file in files:
        rows=[]
        for line in file.read_text(encoding='utf-8').splitlines():
            try:
                event=json.loads(line)
            except (ValueError,TypeError):
                continue
            if isinstance(event,dict):
                rows.append(event)
        if not rows or not any(e.get('event')=='SESSION_SUMMARY' for e in rows):
            unresolved+=1
        if any(e.get('event')=='UNRESOLVED_POSITION' for e in rows):
            unresolved+=0 if not rows or not any(e.get('event')=='SESSION_SUMMARY' for e in rows) else 1
        for event in rows:
            name=event.get('event')
            if name=='INDEX_SIGNAL':
                types[event.get('strategy','UNKNOWN')]+=1
            elif name=='RISK_PLAN':
                stop=event.get('index_stop_plan') or {}
                plans.append({'timestamp':event.get('timestamp'),
                              'stop_basis':stop.get('basis'),
                              'target_basis':stop.get('target_basis'),
                              'index_stop':stop.get('index_stop'),
                              'index_target':stop.get('index_target'),
                              'index_risk_points':stop.get('index_risk_points'),
                              'index_reward_points':stop.get('index_reward_points'),
                              'remaining_daily_risk':event.get('remaining_daily_risk_inr'),
                              'risk_budget':event.get('risk_budget'),
                              'max_trade_loss_inr':event.get('max_trade_loss_inr')})
            elif name=='STRUCTURE_REJECTED':
                summary['credit_structure_rejections']+=1
                if event.get('fallback')=='TRY_NON_EXPIRING_LONG_OPTION':
                    summary['long_fallback_attempts']+=1
                structures.append({'timestamp':event.get('timestamp'),
                                   'structure':event.get('trade_structure'),
                                   'reason':str(event.get('reason','UNKNOWN'))[:300],
                                   'fallback':event.get('fallback')})
            elif name=='OPTION_SELECTION':
                if event.get('fallback_from_credit'):
                    summary['long_fallback_selections']+=1
            elif name in ('SIGNAL_REJECTED','CONTRACT_FILTER_BLOCKED'):
                reason=event.get('message') or event.get('reason') or 'UNKNOWN'
                rejects[str(reason)[:500]]+=1
            elif name=='MARKET_DATA_ERROR':
                errors.append({'timestamp':event.get('timestamp'),
                               'message':str(event.get('message','UNKNOWN'))[:300]})
            elif name=='PAPER_SPREAD_OPEN':
                summary['credit_spread_opens']+=1
            elif name=='PAPER_BUY_FILLED':
                summary['long_option_fills']+=1
            elif name=='PAPER_TRADE_CLOSED':
                summary['closed_trades']+=1
                pnl+=float(event.get('net_pnl') or 0)
    summary['signals']=sum(types.values())
    summary['signals_by_strategy']=dict(types)
    summary['risk_plans']=len(plans)
    summary['recent_risk_plans']=plans[-8:]
    summary['recent_structure_rejections']=structures[-8:]
    summary['net_realized_paper_pnl']=round(pnl,2)
    summary['pending_or_unresolved_sessions']=unresolved
    summary['rejections']=[{'count':count,'reason':reason} for reason,count in rejects.most_common(12)]
    summary['market_data_errors']=len(errors)
    summary['recent_market_data_errors']=errors[-5:]
    return summary
