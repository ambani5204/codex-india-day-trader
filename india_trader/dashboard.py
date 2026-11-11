"""Mobile-friendly, READ-ONLY dashboard for simulation journals.

Only static HTML and sanitized aggregates are exposed. Bind loopback by default.
For public access use TLS reverse proxy and HTTP Basic auth; no credentials in URLs.
"""
from __future__ import annotations
import base64
import datetime as dt
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .core import IST
from .report import summary_from_folder
from .paper_sim import money

WEB_FILE=Path(__file__).resolve().parent.parent/'web/dashboard.html'


def read_journals(folder):
    sessions=[]; trades=[];latest_quote=None; fees_breakdown={}
    for p in sorted(Path(folder).glob('*.jsonl')):
        data=[]
        with p.open(encoding='utf8') as f:
            for line in f:
                try:
                    item=json.loads(line)
                    if isinstance(item,dict):data.append(item)
                except ValueError:pass
        if not data:continue
        meta=next((e for e in data if e.get('event')=='SESSION_START'),data[0])
        session={'name':p.stem,'date':str(meta.get('timestamp',''))[:10],
                 'market':meta.get('market','UNKNOWN'),
                 'data_source':meta.get('source','UNKNOWN'),
                 'last_event':data[-1].get('event','UNKNOWN'),
                 'unresolved':any(e.get('event')=='PAPER_BUY_FILLED' for e in data) and not any(e.get('event')=='PAPER_TRADE_CLOSED' for e in data),
                 'last_update':data[-1].get('timestamp')}
        sessions.append(session)
        quotes=[e for e in data if e.get('event')=='QUOTE_SNAPSHOT']
        if quotes:
            recent=quotes[-1]
            if not latest_quote or (recent.get('timestamp','')>latest_quote.get('timestamp','')):
                latest_quote={'market':meta.get('market','UNKNOWN'),'bid':recent.get('bid'),
                              'ask':recent.get('ask'),'timestamp':recent.get('timestamp'),
                              'captured_at':recent.get('captured_at')}
        for t in data:
            if t.get('event')!='PAPER_TRADE_CLOSED':continue
            trade={'date':str(t.get('timestamp',''))[:10], 'closed_at':t.get('timestamp'),
                   'market':t.get('market','UNKNOWN'), 'symbol':t.get('symbol',''),
                   'buy':t.get('buy_price'),'sell':t.get('sell_price'),'quantity':t.get('quantity'),
                   'gross':t.get('gross_pnl'),'charges':t.get('fees',{}).get('total'),
                   'net':t.get('net_pnl'),'reason':t.get('reason'),
                   'fee_profile':t.get('fees',{}).get('broker_profile','ZERODHA')}
            trades.append(trade)
            for key,val in t.get('fees',{}).items():
                if key in {'brokerage','stt','exchange_transaction_charge','gst','sebi','ipft','stamp_duty'}:
                    fees_breakdown[key]=money(fees_breakdown.get(key,0)+float(val))
    trades.sort(key=lambda x:x['closed_at'] or '')
    sessions.sort(key=lambda x:x['name'],reverse=True)
    return sessions,trades,latest_quote,fees_breakdown


def dashboard_payload(folder='trader/demo_forward', mode='demo', monthly_cost=0):
    if mode not in {'demo','upstox'}:raise ValueError('Invalid dashboard mode')
    s,t,q,fees=read_journals(folder)
    report=summary_from_folder(folder,monthly_cost)
    cumulative=0;series=[]
    for trade in t:
        cumulative=money(cumulative+float(trade['net']))
        series.append({'date':trade['closed_at'],'net':cumulative})
    return {'mode':mode.upper(),'is_demo':mode=='demo','source':str(folder),
            'updated_at':dt.datetime.now(IST).isoformat(),
            'report':report,'series':series,'sessions':s[:25], 'trades':list(reversed(t[-40:])),
            'fees_breakdown':fees,'latest_quote':q,
            'caveat':'All DEMO data is synthetically invented; no real market evidence.' if mode=='demo' else
            'All fills are estimates from Upstox snapshot quotes, not exchange executions. No live orders.'}


def serve_dashboard(host='127.0.0.1',port=8080,folder='trader/demo_forward',mode='demo',monthly_cost=0):
    username=os.environ.get('DASHBOARD_USERNAME','')
    password=os.environ.get('DASHBOARD_PASSWORD','')
    if host not in {'127.0.0.1','::1','localhost'} and (not username or not password or len(password)<16):
        raise ValueError('Public/interface binding requires DASHBOARD_USERNAME and DASHBOARD_PASSWORD (16+ chars)')
    page=WEB_FILE.read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def _auth(self):
            if not password and not username:return True
            header=self.headers.get('Authorization','')
            expected='Basic '+base64.b64encode((username+':'+password).encode()).decode()
            return hmac.compare_digest(header,expected)

        def do_GET(self):
            if not self._auth():
                self.send_response(401)
                self.send_header('WWW-Authenticate','Basic realm="Day Trader Paper Dashboard"')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                return
            path=urlsplit(self.path).path
            if path=='/' or path=='/index.html':
                body=page;mime='text/html; charset=utf-8'
            elif path=='/api/status':
                body=json.dumps(dashboard_payload(folder,mode,monthly_cost),ensure_ascii=False).encode()
                mime='application/json; charset=utf-8'
            elif path=='/health':
                body=json.dumps({'ok':True,'mode':mode,'note':'Server health, NOT market connectivity'}).encode()
                mime='application/json'
            else:
                self.send_error(404);return
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store, private')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self,fmt,*args):
            # Avoid logging credentials, queries, client paths. No auth tokens are ever returned.
            return

    server=ThreadingHTTPServer((host,port),Handler)
    print(f'PAPER dashboard at http://{host}:{port} ({mode.upper()}). HTTPS reverse proxy required for internet exposure.',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
