#!/usr/bin/env python3
"""Unattended read-only Upstox paper-market scheduler for an always-on Linux VPS.

Start automatically each weekday 09:15-09:30 IST. One market selected by
the user's fixed weekly rule. No broker order endpoints. No retrospective fills.
This is not an exchange holiday calendar. Do not use on a public endpoint.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from india_trader.core import IST
from india_trader.schedule import market_for_day

LOG_DIR=ROOT/'trader'
LOG_DIR.mkdir(exist_ok=True)
LOCK_FILE=LOG_DIR/'cloud_runner.lock'


def _run(*argv):
    args=[sys.executable,str(ROOT/'tools'/'india.py'),*argv]
    result=subprocess.run(args,cwd=ROOT,check=False)
    return result.returncode


def ensure_paper_config():
    path=ROOT/'trader'/'config.json'
    if path.exists():
        data=json.loads(path.read_text())
    else:
        data=json.loads((ROOT/'trader'/'config.example.json').read_text())
    if data.get('allow_live_orders'):
        raise RuntimeError('Live order setting is not permitted by paper scheduler')
    data['paper']=True
    data['allow_live_orders']=False
    data['allow_derivatives']=True
    if not path.exists():
        path.write_text(json.dumps(data,indent=2)+'\n')
        path.chmod(0o600)
    return data


def run_day(day, market):
    if not os.environ.get('UPSTOX_ACCESS_TOKEN'):
        print('ERROR: missing UPSTOX_ACCESS_TOKEN in private server environment',flush=True)
        return
    print(f'{day} {market}: syncing Upstox instruments',flush=True)
    if _run('upstox-sync')!=0:
        print(f'{day} {market}: instrument sync failed, no session',flush=True)
        return
    print(f'{day} {market}: starting quote-based paper session',flush=True)
    try:
        code=_run('paper-upstox','--market',market,'--lots','1','--selector','delta',
                  '--delta-min','0.40','--delta-max','0.65','--target-delta','0.50',
                  '--fee-profile','UPSTOX')
        print(f'{day} {market}: worker returned {code}',flush=True)
    finally:
        _run('db-sync')
        print(f'{day} {market}: journal archive refreshed',flush=True)


def main():
    os.chdir(ROOT)
    ensure_paper_config()
    lock=open(LOCK_FILE,'a+')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another paper scheduler is running; stopping duplicate',flush=True)
        return 1
    print('Automatic paper scheduler running; weekdays 09:15 IST; no live orders',flush=True)
    attempted_day=None
    while True:
        now=dt.datetime.now(IST)
        day=now.date()
        market=market_for_day(day)
        if market and dt.time(9,15)<=now.time()<dt.time(9,30) and day!=attempted_day:
            attempted_day=day
            try:
                run_day(day,market)
            except Exception as exc:
                print(f'{day} {market}: scheduler error: {exc.__class__.__name__}: {exc}',flush=True)
        # Historical sessions remain available even if the worker or phone stops.
        time.sleep(12)


if __name__=='__main__':
    raise SystemExit(main())
