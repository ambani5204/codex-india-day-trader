"""Termux foreground scheduler: start any time, paper session at next market open.

No daily restart, no fabricated backfills, and no real broker orders.
The phone must remain powered and Android must allow Termux in background.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india_trader.core import IST
from india_trader.schedule import market_for_day
from india_trader.storage import sync_journals, period_report

OPEN = dt.time(9, 15)
LAST_START = dt.time(15, 10)
LOG_DIR = ROOT / 'trader'
STATUS_FILE = LOG_DIR / 'termux_scheduler_status.json'


def next_session(now: dt.datetime, attempted_day: dt.date | None = None):
    """Return (start_datetime, market). An intraday late start is allowed.

    It does not backfill historical paper trades. A stale/missed breakout
    is rejected by the existing Upstox forward-paper worker.
    """
    now = now.astimezone(IST)
    day = now.date()
    market = market_for_day(day)
    if market and day != attempted_day:
        if now.time() < OPEN:
            return dt.datetime.combine(day, OPEN, IST), market
        if now.time() < LAST_START:
            return now, market
    for offset in range(1, 9):
        candidate = day + dt.timedelta(days=offset)
        market = market_for_day(candidate)
        if market:
            return dt.datetime.combine(candidate, OPEN, IST), market
    raise RuntimeError('No next market weekday found')


def write_status(state: str, *, market: str = '', start: str = '', message: str = ''):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        'state': state, 'market': market,
        'next_start': start, 'note': message,
        'updated_at': dt.datetime.now(IST).isoformat(),
    }
    temporary = STATUS_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    temporary.replace(STATUS_FILE)


def ensure_paper_config():
    path = ROOT / 'trader' / 'config.json'
    template = ROOT / 'trader' / 'config.example.json'
    config = json.loads((path if path.exists() else template).read_text(encoding='utf-8'))
    if config.get('allow_live_orders'):
        raise RuntimeError('Refusing to start: allow_live_orders must be false')
    config['paper'] = True
    config['allow_derivatives'] = True
    config['allow_live_orders'] = False
    path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def command(*args, log=None):
    argv = [sys.executable, str(ROOT / 'tools' / 'india.py'), *args]
    if log:
        with open(log, 'a', encoding='utf-8') as output:
            worker = subprocess.Popen(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
            try:
                while worker.poll() is None:
                    # Heartbeat and incremental SQLite import while market data arrives.
                    write_status('RUNNING', market=args[2] if len(args)>2 and args[1]=='--market' else '',
                                 message='Upstox paper-trading worker running')
                    sync_journals(LOG_DIR / 'paper_upstox', LOG_DIR / 'paper.sqlite3')
                    time.sleep(20)
                return worker.returncode
            finally:
                if worker.poll() is None:
                    worker.terminate()
                    try:
                        worker.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        worker.kill()
                        worker.wait()
    return subprocess.run(argv, cwd=ROOT).returncode


def run_session(day: dt.date, market: str):
    if not os.environ.get('UPSTOX_ACCESS_TOKEN'):
        raise RuntimeError('Missing Upstox token; restart the launcher and enter a token locally')
    print(f'{dt.datetime.now(IST):%d %b %H:%M} · Preparing {market} paper session', flush=True)
    write_status('PREPARING', market=market, message='Downloading current instrument master')
    if command('upstox-sync') != 0:
        write_status('ERROR', market=market, message='Instrument sync failed; see Termux')
        print('Instrument sync failed; next attempt will be the next weekday.', flush=True)
        return
    log_path = LOG_DIR / ('upstox_' + market.lower() + '.log')
    write_status('RUNNING', market=market, message='Upstox paper session in progress')
    print(f'Started {market} paper trading. Log: {log_path}', flush=True)
    mode=os.environ.get('PAPER_MODE','orb').strip().lower()
    if mode not in ('orb','advanced'):
        raise RuntimeError('PAPER_MODE must be orb or advanced')
    try:
        if mode=='advanced':
            print('Experimental all-day multi-strategy paper mode (no broker orders)',flush=True)
            result=command('paper-advanced','--market',market,
                           '--poll-seconds','30','--cooldown-minutes','15',log=log_path)
        else:
            result=command('paper-upstox', '--market', market, '--lots', '1',
                           '--selector', 'delta', '--delta-min', '0.40',
                           '--delta-max', '0.65', '--target-delta', '0.50',
                           '--fee-profile', 'UPSTOX', log=log_path)
        print(f'{market} paper session ended (code {result}).', flush=True)
    finally:
        sync_journals(LOG_DIR / 'paper_upstox', LOG_DIR / 'paper.sqlite3')
    report = period_report('day', day.isoformat(), LOG_DIR / 'paper.sqlite3')
    print(f"{day} · {report['trades']} closed paper trades · Net ₹{report['net_pnl']:.2f}", flush=True)
    if result != 0:
        message=(f'{market} worker exited with code {result}, no normal session completion. '
                 f'Check {log_path} for the specific startup/trading error.')
        print('ERROR: '+message, flush=True)
        write_status('ERROR', market=market, message=message)
        return
    write_status('FINISHED', market=market,
                 message=f"Session ended, {report['trades']} closed trades; next weekday is scheduled automatically")


def main():
    os.chdir(ROOT)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ensure_paper_config()
    if not os.environ.get('UPSTOX_ACCESS_TOKEN'):
        raise RuntimeError('Missing token. Start using bash start-anytime.sh')
    lock = open(LOG_DIR / 'termux_runner.lock', 'a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another overnight scheduler is already running.', flush=True)
        return 1
    attempted = None
    previous_wait = None
    last_heartbeat = None
    print('Overnight scheduler active. Start time: 09:15 IST on weekdays.', flush=True)
    try:
        while True:
            now = dt.datetime.now(IST)
            start, market = next_session(now, attempted)
            if start > now:
                label = (start.isoformat(), market)
                if label != previous_wait:
                    print(f'Waiting for {market} — {start:%a %d %b %I:%M %p} IST', flush=True)
                    previous_wait = label
                if last_heartbeat is None or (now-last_heartbeat).total_seconds() >= 60:
                    write_status('WAITING', market=market, start=start.isoformat(),
                                 message='Termux must remain running in background')
                    last_heartbeat = now
                time.sleep(min(20.0, max(1.0, (start-now).total_seconds())))
                continue
            day = now.date()
            attempted = day
            previous_wait = None
            try:
                run_session(day, market)
            except Exception as exc:
                print(f'Session error: {type(exc).__name__}: {exc}', flush=True)
                write_status('ERROR', market=market, message=str(exc)[:200])
                try:
                    sync_journals(LOG_DIR / 'paper_upstox', LOG_DIR / 'paper.sqlite3')
                except Exception:
                    pass
            # After any outcome, the next loop waits for a *future* market day.
    except KeyboardInterrupt:
        print('Scheduler stopped by user.', flush=True)
        write_status('STOPPED', message='Restart using bash start-anytime.sh')
    finally:
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
