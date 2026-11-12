"""Indian index intraday signals and strictly defined-risk option credit spreads.

Experimental PAPER-ONLY research engine. Never place broker orders. Data must
be complete closed 5-minute index candles + live Upstox option-chain quotes.
"""
from __future__ import annotations
import datetime as dt
from statistics import mean
from .core import IST
from .upstox import INDICES, EXCHANGES, UpstoxError, normalize_expiry
from .paper_sim import option_fees, money


def ema(values, window):
    if not values or window < 1:
        raise ValueError('EMA needs price history')
    alpha = 2 / (window + 1)
    result = float(values[0])
    for price in values[1:]:
        result += alpha * (float(price) - result)
    return result


def intraday_signal(bars, now, last_bar=None):
    """ORB + EMA trend continuation + oversold/overbought reversal.

    Only use a genuinely just-closed 5-minute candle. No forward-looking data.
    Non-strategy intervals and stale/missing data always yield no signal.
    """
    now = now.astimezone(IST)
    if not (dt.time(9,35) <= now.time() < dt.time(14,40)) or now.weekday() >= 5:
        return None
    closed = sorted((b for b in bars if b.time.date() == now.date()
                     and b.time + dt.timedelta(minutes=5) <= now), key=lambda b:b.time)
    if len(closed) < 4:
        return None
    last = closed[-1]
    end = last.time + dt.timedelta(minutes=5)
    if last_bar is not None and last.time <= last_bar:
        return None
    if (now - end).total_seconds() > 90 or (now - end).total_seconds() < 0:
        return None
    prices = [b.close for b in closed]
    opening = [b for b in closed if b.time.time() in
               (dt.time(9,15), dt.time(9,20), dt.time(9,25))]
    if len(opening) < 3:
        return None
    high = max(b.high for b in opening)
    low = min(b.low for b in opening)
    previous = closed[-2]
    if last.close > high and previous.close <= high:
        return {'strategy':'OPENING_RANGE_BREAKOUT','direction':'BULL','strength':2,
                'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    if last.close < low and previous.close >= low:
        return {'strategy':'OPENING_RANGE_BREAKOUT','direction':'BEAR','strength':2,
                'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    if len(prices) < 24:
        return None
    fast = ema(prices[:-1], 8)
    slow = ema(prices[:-1], 21)
    fast_now = ema(prices, 8)
    slow_now = ema(prices, 21)
    # Fresh EMA crossover; do not trade repeatedly while already trending.
    if fast <= slow and fast_now > slow_now and last.close > previous.close:
        return {'strategy':'EMA_8_21_CROSS','direction':'BULL','strength':1,
                'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    if fast >= slow and fast_now < slow_now and last.close < previous.close:
        return {'strategy':'EMA_8_21_CROSS','direction':'BEAR','strength':1,
                'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    # Strict 20-bar mean-reversion: reversal candle after a large deviation,
    # only when EMAs do not show a powerful trend (> 0.25% divergence).
    if abs(fast_now / slow_now - 1) < .0025:
        reference=prices[-21:-1]
        avg=mean(reference)
        volatility=(sum((p-avg)**2 for p in reference)/len(reference))**.5
        if volatility > 0:
            if previous.close < avg-2*volatility and last.close > previous.close and last.close < avg:
                return {'strategy':'MEAN_REVERSION','direction':'BULL','strength':1,
                        'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
            if previous.close > avg+2*volatility and last.close < previous.close and last.close > avg:
                return {'strategy':'MEAN_REVERSION','direction':'BEAR','strength':1,
                        'bar':last.time.isoformat(),'confirmed_at':end.isoformat()}
    return None


def _liquid_leg(row, side, qty, max_spread_pct=2):
    """Contract must have enough actual top-of-book bid AND ask quantity."""
    if not isinstance(row, dict):
        return None
    x=row.get(side+'_options') or {}
    d=x.get('market_data') or {}
    try:
        bid=float(d['bid_price'])
        ask=float(d['ask_price'])
        bqty=int(d['bid_qty'])
        aqty=int(d['ask_qty'])
        delta=float((x.get('option_greeks') or {})['delta'])
        key=str(x['instrument_key'])
        if not (0 < bid <= ask and bqty >= qty and aqty >= qty):
            return None
        spread=200*(ask-bid)/(ask+bid)
        if spread > max_spread_pct:
            return None
        return {'key':key,'bid':bid,'ask':ask,'delta':delta,
                'bid_qty':bqty,'ask_qty':aqty,'spread_pct':spread}
    except (KeyError,ValueError,TypeError,ZeroDivisionError):
        return None


def _fees_credit_round_trip(sell_bid,buy_ask,short_exit,long_exit,qty,exchange):
    # Short leg: premium sold now and bought back later.
    # Long protection: bought now and sold later.
    short_fees=option_fees(short_exit,sell_bid,qty,exchange,'UPSTOX')['total']
    hedge_fees=option_fees(buy_ask,long_exit,qty,exchange,'UPSTOX')['total']
    return money(short_fees+hedge_fees)


def select_credit_spread(records,chain,market,direction,spot,today,settings,expiry=None,
                         lots=1,max_spread_pct=2):
    """Sell an OTM option, simultaneously buy a farther-OTM protective option.

    Credit spread max expiry payoff loss is strike-width less net credit, plus
    estimated fees, but intra-session gap/fill and broker margin can differ.
    NEVER naked short options. Same-day expiry is paper-only and MUST be closed
    before the engine's conservative cutoff.
    """
    if direction not in ('BULL','BEAR') or market not in INDICES or spot<=0:
        raise UpstoxError('Invalid market, spot or direction for spread')
    if not (settings.get('paper',True) and not settings.get('allow_live_orders')):
        raise UpstoxError('Live trades are blocked')
    side='put' if direction=='BULL' else 'call'
    opt_type='PE' if side=='put' else 'CE'
    expected_delta=(-.25 if side=='put' else .25)
    seg,exchange=EXCHANGES[market]
    valid={}
    for r in records:
        if r.get('segment')!=seg or r.get('instrument_type')!=opt_type:
            continue
        if r.get('underlying_key')!=INDICES[market]:
            u=str(r.get('underlying_symbol','')).upper()
            if u not in ({'NIFTY','NIFTY 50'} if market=='NIFTY' else {'SENSEX'}):
                continue
        try:
            exp=normalize_expiry(r['expiry'])
            if exp < today or (expiry and exp.isoformat()!=expiry):
                continue
            key=str(r['instrument_key'])
            valid[key]=r
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    if not valid:
        raise UpstoxError('No eligible current-day spread legs in instrument master')
    rows=[]
    for row in chain:
        try:
            exp=str(row['expiry'])
            strike=float(row['strike_price'])
            if expiry and exp!=expiry:
                continue
            key=(row.get(side+'_options') or {}).get('instrument_key')
            if key not in valid:
                continue
            lot=int(valid[key]['lot_size'])
            qty=lot*lots
            leg=_liquid_leg(row,side,qty,max_spread_pct)
            if not leg:
                continue
            if not (.01 <= abs(leg['delta']) <= .40):
                continue
            if side=='put' and not (leg['delta']<0 and strike<spot):
                continue
            if side=='call' and not (leg['delta']>0 and strike>spot):
                continue
            rows.append({'strike':strike,'expiry':exp,'lot':lot,'qty':qty,'leg':leg})
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    if len(rows)<2:
        raise UpstoxError('No liquid OTM protective spread legs')
    cap=float(settings['max_loss_per_trade_inr'])
    allocation=float(settings['capital_inr'])*float(settings['max_allocation_fraction'])
    ranked=[]
    for short in rows:
        if not (.12 <= abs(short['leg']['delta']) <= .40):
            continue
        for hedge in rows:
            if short is hedge or short['expiry']!=hedge['expiry'] or short['lot']!=hedge['lot']:
                continue
            if abs(hedge['leg']['delta']) >= abs(short['leg']['delta']):
                continue
            width=(short['strike']-hedge['strike']) if side=='put' else (hedge['strike']-short['strike'])
            if not (0 < width <= 200):  # capped wing distance, not unlimited
                continue
            credit=short['leg']['bid']-hedge['leg']['ask']
            if credit<=0:
                continue
            qty=short['qty']
            max_expiry_loss=(width-credit)*qty
            if max_expiry_loss<=0:continue
            # Conservative estimate for 4 legs, not a certified broker margin quote.
            est_fees=_fees_credit_round_trip(short['leg']['bid'],hedge['leg']['ask'],
                             max(width,short['leg']['bid']*2), max(.01,hedge['leg']['bid']*.25),
                             qty,exchange)
            risk=money(max_expiry_loss+est_fees)
            if risk>cap or width*qty>allocation:
                continue
            ranked.append((abs(short['leg']['delta']-expected_delta), width, -credit,
                           {'market':market,'strategy':'DEFINED_RISK_CREDIT_SPREAD',
                            'direction':direction,'option_type':opt_type,
                            'expiry':short['expiry'],'short_key':short['leg']['key'],
                            'long_key':hedge['leg']['key'],
                            'short_strike':short['strike'],'long_strike':hedge['strike'],
                            'short_bid':short['leg']['bid'],'long_ask':hedge['leg']['ask'],
                            'short_delta':short['leg']['delta'],
                            'credit_per_unit':money(credit),'quantity':qty,
                            'width':width,'estimated_max_expiry_loss_after_fees':risk,
                            'margin_not_verified':True,'executable_fill_not_guaranteed':True,
                            'source':'UPSTOX_REST_OPTION_CHAIN_PAPER'}))
    if not ranked:
        raise UpstoxError('No defined-risk credit spread fits risk, premium, delta and liquidity limits')
    return min(ranked,key=lambda e:e[:3])[3]


def spread_mark(position,chain,market,now,stop_multiplier=2,target_fraction=.4):
    """Mark two-leg spread using unfavorable real top-of-book prices."""
    side='put' if position['option_type']=='PE' else 'call'
    legs={}
    for row in chain:
        if not isinstance(row,dict):continue
        leg = row.get(side+'_options') or {}
        key=leg.get('instrument_key')
        if key in (position['short_key'],position['long_key']):
            quote=_liquid_leg(row,side,position['quantity'])
            if quote:legs[key]=quote
    if position['short_key'] not in legs or position['long_key'] not in legs:
        raise UpstoxError('Missing liquid depth on one or both spread legs; cannot mark paper exit')
    short=legs[position['short_key']]
    long=legs[position['long_key']]
    # Conservative close: buy back sold leg at ask; sell hedge at bid.
    exit_debit=short['ask']-long['bid']
    exchange=EXCHANGES[market][1]
    fees=_fees_credit_round_trip(position['short_bid'],position['long_ask'],
                                  short['ask'],long['bid'],position['quantity'],exchange)
    net=money((position['credit_per_unit']-exit_debit)*position['quantity']-fees)
    tm=now.astimezone(IST).time()
    cutoff=dt.time(14,45) if dt.date.fromisoformat(position['expiry'])==now.date() else dt.time(15,15)
    reason=('TIME_EXIT' if tm>=cutoff else
            'CREDIT_STOP' if exit_debit>=position['credit_per_unit']*stop_multiplier else
            'CREDIT_TARGET' if (exit_debit<=position['credit_per_unit']*target_fraction and net>0) else None)
    return {'reason':reason,'net_pnl':net,'fees':fees,
            'exit_debit':money(exit_debit),'bid_long':long['bid'],
            'ask_short':short['ask'],'source':'INDICATIVE_REST_QUOTES_NOT_EXCHANGE_FILLS'}
