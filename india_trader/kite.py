"""Read-only Zerodha Kite Connect v3 REST client. Never sends orders."""
import csv
import gzip
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from .core import Bar, parse_time

BASE='https://api.kite.trade'

class KiteError(RuntimeError): pass

class KiteReader:
    def __init__(self,key=None,token=None):
        self.key=key or os.getenv('KITE_API_KEY')
        self.token=token or os.getenv('KITE_ACCESS_TOKEN')
        if not self.key or not self.token:
            raise KiteError('Set KITE_API_KEY and KITE_ACCESS_TOKEN in your terminal environment (not chat or repo).')

    def get(self,path,params=None,csv_response=False):
        encoded=urllib.parse.urlencode(params or {},doseq=True)
        url=BASE+path+('?' + encoded if encoded else '')
        req=urllib.request.Request(url,headers={
            'Authorization':f'token {self.key}:{self.token}',
            'X-Kite-Version':'3','User-Agent':'CodexIndiaDayTrader/0.1'})
        try:
            with urllib.request.urlopen(req,timeout=20) as resp:
                b=resp.read()
                if b[:2]==b'\x1f\x8b':b=gzip.decompress(b)
                if csv_response:return b.decode('utf-8-sig')
                result=json.loads(b)
                if result.get('status')!='success':raise KiteError(result.get('message','Kite API error'))
                return result.get('data')
        except urllib.error.HTTPError as exc:
            # Do not expose tokens, headers or URL query strings.
            raise KiteError(f'Kite HTTP {exc.code}; check API permissions or session token') from None
        except urllib.error.URLError as exc:
            raise KiteError(f'Could not reach Kite API: {exc.reason}') from None

    def instruments(self,exchange=None):
        p='/instruments'+('/'+exchange if exchange else '')
        return list(csv.DictReader(io.StringIO(self.get(p,csv_response=True))))

    def quotes(self,symbols):
        return self.get('/quote/ltp', {'i':symbols})

    def full_quotes(self,symbols):
        """Read-only full quote snapshots incl. five-level bid/ask depth."""
        return self.get('/quote', {'i':symbols})

    def candles(self,instrument_token,day,interval='5minute',start=None,end=None):
        start=start or day+' 09:15:00'
        end=end or day+' 15:30:00'
        return self.candles_range(instrument_token,start,end,interval)

    def candles_range(self,instrument_token,start,end,interval='5minute'):
        rows=self.get('/instruments/historical/'+str(int(instrument_token))+'/'+interval,
                      {'from':start,'to':end,'continuous':0,'oi':0}).get('candles',[])
        return [Bar(parse_time(row[0]),*map(float,row[1:5]),float(row[5])) for row in rows]


def save_master(reader,path):
    csvtext=reader.get('/instruments',csv_response=True)
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(csvtext,encoding='utf-8')
    return sum(1 for _ in csv.DictReader(io.StringIO(csvtext)))


def find_instrument(path,symbol):
    if ':' not in symbol:raise ValueError('Use EXCHANGE:TRADINGSYMBOL, e.g. NSE:NIFTY 50 or BSE:SENSEX')
    exchange,name=symbol.split(':',1)
    with open(path,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r['exchange']==exchange and r['tradingsymbol']==name:
                return r
    raise ValueError('Not found in cached instrument master: '+symbol+'; run instruments sync')
