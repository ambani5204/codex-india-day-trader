"""Read-only Upstox V3 REST market-data adapter; NO order endpoints.

URLs follow official V3 quote/candle docs. A REST snapshot is not a WebSocket
or an exchange execution; stale quotes and missing liquidity are rejected.
"""
from __future__ import annotations
import datetime as dt
import gzip
import json
import os
from pathlib import Path
from urllib.parse import quote as urlencode_path, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .core import Bar, IST, parse_time
from .paper_sim import Quote

INDICES = {'NIFTY': 'NSE_INDEX|Nifty 50', 'SENSEX': 'BSE_INDEX|SENSEX'}
EXCHANGES = {'NIFTY': ('NSE_FO', 'NFO'), 'SENSEX': ('BSE_FO', 'BFO')}
BOD_URL = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'
API_BASE = 'https://api.upstox.com'


class UpstoxError(ValueError):
    pass


def _json_request(url, token=None):
    headers = {'Accept':'application/json','User-Agent':'CodexIndiaPaperSim/1.0'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req=Request(url,headers=headers,method='GET')
    try:
        with urlopen(req,timeout=16) as res:
            content=res.read()
    except HTTPError as exc:
        # Never echo arbitrary broker response containing user data or credentials.
        raise UpstoxError(f'Upstox HTTP {exc.code} - check token, entitlements, and API limits') from None
    except (URLError,TimeoutError) as exc:
        raise UpstoxError('Upstox connection timed out or network unavailable') from exc
    try:
        if url.endswith('.gz'):
            content=gzip.decompress(content)
        result=json.loads(content)
    except (ValueError,OSError) as exc:
        raise UpstoxError('Upstox sent unreadable instrument or market data') from exc
    if isinstance(result,dict) and result.get('status')=='error':
        raise UpstoxError('Upstox API returned an error; verify token and permission')
    return result


def normalize_expiry(value):
    """Upstox BOD expiry is epoch milliseconds, but tolerate YYYY-MM-DD."""
    if isinstance(value,(int,float)):
        return dt.datetime.fromtimestamp(value/1000,IST).date()
    if isinstance(value,str):
        if value.isdigit():return dt.datetime.fromtimestamp(int(value)/1000,IST).date()
        return dt.date.fromisoformat(value[:10])
    raise ValueError('Invalid expiry')


def select_atm(records, market, side, spot, today):
    if market not in INDICES or side not in {'BUY','SELL'} or spot<=0:
        raise UpstoxError('Invalid market, signal, or spot price')
    segment,exchange=EXCHANGES[market]
    opt_type='CE' if side=='BUY' else 'PE'
    # Avoid expiry-day settlement and intraday expiry liquidity artifacts.
    candidates=[]
    for row in records:
        if row.get('segment')!=segment or row.get('instrument_type')!=opt_type:
            continue
        underlying=str(row.get('underlying_symbol','')).upper()
        underlying_key=row.get('underlying_key')
        if not (underlying_key==INDICES[market] or (market=='NIFTY' and underlying in {'NIFTY','NIFTY 50'}) or (market=='SENSEX' and underlying=='SENSEX')):
            continue
        try:
            expiry=normalize_expiry(row['expiry'])
            strike=float(row['strike_price']); lot=int(row['lot_size'])
            if expiry<=today or strike<=0 or lot<=0 or not row.get('instrument_key'):
                continue
            candidates.append((expiry,abs(strike-spot),strike,str(row['instrument_key']),row,lot))
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    if not candidates:
        raise UpstoxError('No non-expiring eligible option found in current Upstox instrument master')
    expiry,distance,strike,key,row,lot=min(candidates,key=lambda c:c[:4])
    return {'instrument_key':key,'expiry':expiry.isoformat(),'strike':strike,
            'lot_size':lot,'market':market,'exchange':exchange,'option_type':opt_type,
            'symbol':f'{exchange}:{market}_{strike:g}_{expiry.isoformat()}_{opt_type}',
            'trading_symbol':row.get('trading_symbol',''),'selection':'NEAREST_EXPIRY_NEAREST_ATM_STRIKE',
            'underlying_spot_at_signal':spot}



def select_delta_contract(records, chain, market, side, spot, today, settings, lots=1,
                          stop_pct=15, max_spread_pct=2, fee_profile='UPSTOX',
                          delta_min=0.40, delta_max=0.65, target_delta=0.50):
    """Select a real, unexpired option using option-chain Greeks, premium and visible liquidity.

    No delta/quote/depth data -> no candidate. Risk includes estimated exit
    costs at the hypothetical stop price, and is checked again at live fill.
    Never select a contract expiring *today*: expiry settlement is not modeled.
    """
    from .paper_sim import option_fees
    if not (0 < delta_min <= target_delta <= delta_max < 1):
        raise UpstoxError('Invalid delta band; require 0 < min <= target <= max < 1')
    if int(lots) != lots or lots <= 0 or not 0 < stop_pct < 100 or max_spread_pct <= 0:
        raise UpstoxError('Invalid lot, stop or spread setting')
    preferred = select_atm(records, market, side, spot, today)
    expiry = preferred['expiry']
    kind = preferred['option_type']
    segment, exchange = EXCHANGES[market]
    valid = {}
    for row in records:
        if row.get('segment') != segment or row.get('instrument_type') != kind:
            continue
        underlying = str(row.get('underlying_symbol', '')).upper()
        if row.get('underlying_key') != INDICES[market] and not (
            (market == 'NIFTY' and underlying in {'NIFTY', 'NIFTY 50'}) or
            (market == 'SENSEX' and underlying == 'SENSEX')
        ):
            continue
        try:
            if normalize_expiry(row['expiry']).isoformat() != expiry:
                continue
            key = str(row['instrument_key'])
            lot = int(row['lot_size'])
            if not key or lot <= 0:
                continue
            valid[key] = row
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    if not isinstance(chain, list) or not chain:
        raise UpstoxError('Upstox option chain missing; delta selection blocked')
    capital = float(settings['capital_inr'])
    max_loss = float(settings['max_loss_per_trade_inr'])
    max_allocation = float(settings['max_allocation_fraction'])
    candidates = []
    for strike_row in chain:
        if not isinstance(strike_row, dict) or strike_row.get('expiry') != expiry:
            continue
        entry = strike_row.get('call_options' if kind == 'CE' else 'put_options') or {}
        key = str(entry.get('instrument_key') or '')
        if key not in valid:
            continue
        greeks = entry.get('option_greeks') or {}
        market_data = entry.get('market_data') or {}
        try:
            raw_delta = float(greeks['delta'])
            if not (raw_delta > 0 if kind == 'CE' else raw_delta < 0):
                continue
            delta = abs(raw_delta)
            if not delta_min <= delta <= delta_max:
                continue
            ask = float(market_data['ask_price'])
            bid = float(market_data['bid_price'])
            ask_qty = int(market_data['ask_qty'])
            bid_qty = int(market_data['bid_qty'])
            lot_size = int(valid[key]['lot_size'])
            strike = float(valid[key]['strike_price'])
            quantity = lot_size * int(lots)
            if not (0 < bid <= ask and ask_qty >= quantity and bid_qty >= quantity):
                continue
            spread = 200 * (ask-bid) / (ask+bid)
            if spread > max_spread_pct:
                continue
            premium_outlay = ask * quantity
            if premium_outlay > capital * max_allocation:
                continue
            stop = max(0.01, ask * (1 - stop_pct / 100))
            loss = (ask-stop)*quantity + option_fees(ask, stop, quantity, exchange, fee_profile)['total']
            if loss > max_loss:
                continue
            iv = greeks.get('iv')
            theta = greeks.get('theta')
            selection = {
                'instrument_key': key, 'expiry': expiry, 'strike': strike,
                'lot_size': lot_size, 'market': market, 'exchange': exchange,
                'option_type': kind,
                'symbol': f'{exchange}:{market}_{strike:g}_{expiry}_{kind}',
                'trading_symbol': valid[key].get('trading_symbol', ''),
                'selection': 'LIVE_CHAIN_DELTA_PREMIUM_LIQUIDITY_RISK',
                'underlying_spot_at_signal': spot,
                'delta': raw_delta, 'iv': iv, 'theta': theta,
                'gamma': greeks.get('gamma'), 'vega': greeks.get('vega'),
                'quoted_bid': bid, 'quoted_ask': ask, 'quoted_spread_pct': round(spread, 3),
                'quoted_bid_qty': bid_qty, 'quoted_ask_qty': ask_qty,
                'premium_outlay_at_ask': round(premium_outlay, 2),
                'estimated_stop_loss_including_charges': round(loss, 2),
                'delta_target': target_delta, 'delta_band': [delta_min, delta_max],
                'expiry_day_trade': False,
            }
            rank = (abs(delta-target_delta), abs(strike-spot), spread, premium_outlay, key)
            candidates.append((rank, selection))
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            continue
    if not candidates:
        raise UpstoxError('No contract passed live delta, premium/risk, spread and depth checks; no paper entry')
    return min(candidates, key=lambda item: item[0])[1]


def sync_instruments(path='trader/upstox_instruments.json', today=None):
    result=_json_request(BOD_URL)
    if not isinstance(result,list):raise UpstoxError('Expected Upstox instrument JSON list')
    # Store the two target indices and their derivative contracts only.
    allowed=[]
    for row in result:
        if not isinstance(row,dict):continue
        segment=row.get('segment'); underlying=str(row.get('underlying_symbol','')).upper()
        if (row.get('instrument_key') in INDICES.values() or
            (segment=='NSE_FO' and underlying in {'NIFTY','NIFTY 50'} and row.get('instrument_type') in {'CE','PE'}) or
            (segment=='BSE_FO' and underlying=='SENSEX' and row.get('instrument_type') in {'CE','PE'})):
            allowed.append(row)
    if not allowed:raise UpstoxError('No expected NIFTY/SENSEX instruments returned')
    day=today or dt.datetime.now(IST).date()
    data={'asof':day.isoformat(),'source':BOD_URL,'records':allowed}
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temp.replace(dest)
    return {'date':day.isoformat(),'records':len(allowed),'path':str(dest)}


def load_today_master(path='trader/upstox_instruments.json',today=None):
    try: master=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise UpstoxError('No instrument master; run upstox-sync') from exc
    day=today or dt.datetime.now(IST).date()
    if master.get('asof')!=day.isoformat():raise UpstoxError('Instrument master date stale; run upstox-sync today')
    return master['records']


def quote_from_upstox(data):
    """Convert full quote. Last trade timestamp, not HTTP arrival, gates freshness.

    The quote snapshot timestamp is not evidence that bid/ask changed recently;
    conservatively use the OLDER of snapshot and last-trade times.
    """
    if not data or not data.get('timestamp'):
        raise UpstoxError('Missing quote timestamp')
    timestamp=parse_time(str(data['timestamp']))
    ltt=data.get('last_trade_time')
    if ltt:
        try:
            trade=dt.datetime.fromtimestamp(int(ltt)/1000,IST)
            timestamp=min(timestamp,trade)
        except (ValueError,TypeError,OverflowError):
            raise UpstoxError('Invalid last_trade_time') from None
    depth=data.get('depth') or {}
    def levels(side):
        return tuple((float(row['price']),int(row['quantity'])) for row in depth.get(side,[])
                     if float(row.get('price') or 0)>0 and int(row.get('quantity') or 0)>0)
    bids,asks=levels('buy'),levels('sell')
    if not bids or not asks: raise UpstoxError('No positive bid and ask depth; fill blocked')
    return Quote(timestamp,bids[0][0],asks[0][0],bids[0][1],asks[0][1],
                 float(data.get('last_price') or 0),bids,asks)


class UpstoxReader:
    def __init__(self, token=None):
        self.token=token or os.environ.get('UPSTOX_ACCESS_TOKEN')
        if not self.token:raise UpstoxError('Set UPSTOX_ACCESS_TOKEN locally after official Upstox OAuth login; never paste it into chat')

    def get(self, path, query=None):
        url=API_BASE+path
        if query:url+='?'+urlencode(query)
        response=_json_request(url,self.token)
        if not isinstance(response,dict) or response.get('status')!='success':
            raise UpstoxError('Unexpected Upstox API response')
        return response.get('data')

    def candles(self, index_key):
        data=self.get('/v3/historical-candle/intraday/'+urlencode_path(index_key,safe='')+'/minutes/5')
        if not isinstance(data,dict):raise UpstoxError('Missing candle data')
        rows=data.get('candles') or []
        bars=[]
        for row in rows:
            try:bars.append(Bar(parse_time(str(row[0])),*(float(x) for x in row[1:5]),float(row[5])))
            except (IndexError,TypeError,ValueError):continue
        return sorted(bars,key=lambda b:b.time)

    def option_chain(self, index_key, expiry):
        """Read-only contract chain: premium, quote depth, IV and Greeks."""
        result=self.get('/v2/option/chain',{'instrument_key':index_key,'expiry_date':expiry})
        if not isinstance(result,list):
            raise UpstoxError('Upstox option chain was not a list; selection blocked')
        return result

    def full_quote(self,instrument_key):
        data=self.get('/v3/market-quote/quotes',{'instrument_key':instrument_key})
        if not isinstance(data,dict):raise UpstoxError('Missing quote map')
        matches=[row for row in data.values() if isinstance(row,dict) and row.get('instrument_token')==instrument_key]
        if len(matches)!=1:raise UpstoxError('Contract key missing/ambiguous in Upstox quote response')
        return quote_from_upstox(matches[0])
