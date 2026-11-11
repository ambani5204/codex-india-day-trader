"""Durable, incremental SQLite journal archive and daily/monthly paper results.

The JSONL journals remain the raw audit trail (including quote snapshots).
SQLite stores session metadata, non-quote events and closed paper trades.
No API credentials are ever stored here. Standard-library-only implementation.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from .core import IST

DEFAULT_DB = 'trader/paper.sqlite3'
DEFAULT_JOURNALS = 'trader/paper_upstox'

_SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sessions (
  journal TEXT PRIMARY KEY, day TEXT NOT NULL, market TEXT NOT NULL,
  started_at TEXT, updated_at TEXT, status TEXT NOT NULL DEFAULT 'RUNNING',
  symbol TEXT, expiry TEXT, strike REAL, option_type TEXT, delta REAL,
  ask_premium REAL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, journal TEXT NOT NULL, timestamp TEXT,
  event_type TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
  event_id TEXT PRIMARY KEY, journal TEXT NOT NULL, day TEXT NOT NULL,
  market TEXT NOT NULL, closed_at TEXT, symbol TEXT,
  entry_price REAL, exit_price REAL, quantity INTEGER,
  gross_pnl REAL NOT NULL, fees REAL NOT NULL, net_pnl REAL NOT NULL,
  exit_reason TEXT
);
CREATE TABLE IF NOT EXISTS import_offsets (
  journal TEXT PRIMARY KEY, bytes_processed INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_day ON sessions(day);
CREATE INDEX IF NOT EXISTS idx_trades_day ON trades(day);
'''


def _connect(path):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(p),timeout=15)
    db.executescript(_SCHEMA)
    return db


def sync_journals(directory=DEFAULT_JOURNALS, database=DEFAULT_DB):
    """Import only complete new JSONL lines. Repeated calls never double-count."""
    folder=Path(directory)
    totals={'journals':0,'events':0,'trades':0,'database':str(database)}
    with closing(_connect(database)) as db, db:
        if not folder.exists():
            return totals
        for path in sorted(folder.glob('*.jsonl')):
            if not path.is_file():
                continue
            name=path.name
            parts=path.stem.split('_')
            day=parts[0] if parts else ''
            market=parts[1] if len(parts)>1 else 'UNKNOWN'
            try:
                dt.date.fromisoformat(day)
            except ValueError:
                continue
            prior=db.execute('SELECT bytes_processed FROM import_offsets WHERE journal=?',(name,)).fetchone()
            offset=int(prior[0]) if prior else 0
            if path.stat().st_size<offset:
                # The log was truncated/replaced: clear its imported records first.
                for table in ('trades','events','sessions'):
                    db.execute(f'DELETE FROM {table} WHERE journal=?',(name,))
                offset=0
            db.execute('INSERT OR IGNORE INTO sessions(journal,day,market) VALUES(?,?,?)',(name,day,market))
            with path.open('rb') as handle:
                handle.seek(offset)
                while True:
                    line_start=handle.tell()
                    line=handle.readline()
                    if not line:
                        break
                    if not line.endswith(b'\n'):
                        # Incomplete record from a concurrently writing worker.
                        break
                    offset=handle.tell()
                    try:
                        entry=json.loads(line)
                    except (ValueError,UnicodeDecodeError):
                        continue
                    if not isinstance(entry,dict):
                        continue
                    event=str(entry.get('event',''))
                    timestamp=str(entry.get('timestamp',''))
                    event_id=f'{name}:{line_start}'
                    if event!='QUOTE_SNAPSHOT':
                        before=db.total_changes
                        db.execute('INSERT OR IGNORE INTO events(event_id,journal,timestamp,event_type,details_json) VALUES(?,?,?,?,?)',
                                   (event_id,name,timestamp,event,json.dumps(entry,ensure_ascii=False)))
                        if db.total_changes>before:
                            totals['events']+=1
                    if event=='SESSION_START':
                        db.execute('UPDATE sessions SET started_at=?,updated_at=?,status=? WHERE journal=?',
                                   (timestamp,timestamp,'RUNNING',name))
                    elif event=='INDEX_SIGNAL':
                        contract=entry.get('contract') or {}
                        db.execute('''UPDATE sessions SET symbol=?,expiry=?,strike=?,option_type=?,delta=?,ask_premium=?,updated_at=?
                                      WHERE journal=?''',
                                   (contract.get('symbol'),contract.get('expiry'),contract.get('strike'),
                                    contract.get('option_type'),contract.get('delta'),contract.get('quoted_ask'),
                                    timestamp,name))
                    elif event=='PAPER_TRADE_CLOSED':
                        fees=(entry.get('fees') or {}).get('total',0)
                        before=db.total_changes
                        db.execute('''INSERT OR IGNORE INTO trades
                            (event_id,journal,day,market,closed_at,symbol,entry_price,exit_price,quantity,
                             gross_pnl,fees,net_pnl,exit_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                   (event_id,name,day,market,timestamp,entry.get('symbol'),
                                    entry.get('buy_price'),entry.get('sell_price'),entry.get('quantity'),
                                    float(entry.get('gross_pnl') or 0),float(fees or 0),
                                    float(entry.get('net_pnl') or 0),entry.get('reason')))
                        if db.total_changes>before:
                            totals['trades']+=1
                        db.execute('UPDATE sessions SET updated_at=?,status=? WHERE journal=?',
                                   (timestamp,'CLOSED',name))
                    elif event=='UNRESOLVED_POSITION':
                        db.execute('UPDATE sessions SET updated_at=?,status=? WHERE journal=?',
                                   (timestamp,'UNRESOLVED',name))
                    elif event=='SESSION_SUMMARY':
                        summary=entry.get('summary') or {}
                        status='UNRESOLVED' if summary.get('open_position') else ('CLOSED' if summary.get('closed_trades',0) else 'NO_TRADE')
                        db.execute('UPDATE sessions SET updated_at=?,status=? WHERE journal=?',
                                   (timestamp,status,name))
            db.execute('INSERT INTO import_offsets(journal,bytes_processed) VALUES(?,?) ON CONFLICT(journal) DO UPDATE SET bytes_processed=excluded.bytes_processed',
                       (name,offset))
            totals['journals']+=1
    return totals


def period_report(period='day', value=None, database=DEFAULT_DB):
    """Return realized closed-paper-trade performance; open positions are excluded."""
    if period not in {'day','month'}:
        raise ValueError('Period must be day or month')
    now=dt.datetime.now(IST)
    value=value or (now.date().isoformat() if period=='day' else now.strftime('%Y-%m'))
    if period=='day':
        dt.date.fromisoformat(value)
        where='day=?'
    else:
        dt.date.fromisoformat(value+'-01')
        where='substr(day,1,7)=?'
    with _connect(database) as db:
        sessions=db.execute('SELECT market,status,COUNT(*) FROM sessions WHERE '+where+' GROUP BY market,status',
                            (value,)).fetchall()
        records=db.execute('SELECT day,market,gross_pnl,fees,net_pnl FROM trades WHERE '+where+' ORDER BY closed_at',
                           (value,)).fetchall()
    by_market={}
    by_day={}
    wins=0;gross=fees=net=0.
    for day,market,g,f,n in records:
        gross+=g;fees+=f;net+=n
        wins+=int(n>0)
        for bucket,key in ((by_market,market),(by_day,day)):
            row=bucket.setdefault(key,{'trades':0,'net':0.})
            row['trades']+=1
            row['net']+=n
    for bucket in (by_market,by_day):
        for row in bucket.values():
            row['net']=round(row['net'],2)
    return {
        'period':period,'date':value,'session_count':sum(n for _,_,n in sessions),
        'sessions':[{'market':market,'status':status,'count':n} for market,status,n in sessions],
        'trades':len(records),'wins':wins,
        'win_rate_pct':round(100*wins/len(records),1) if records else None,
        'gross_pnl':round(gross,2),'charges':round(fees,2),'net_pnl':round(net,2),
        'by_market':by_market,'by_day':by_day,
        'basis':'Realized paper trades only, estimated fills and fees, not broker executions',
    }
