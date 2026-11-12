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


def _opening_range_signal(closed, end):
    """Classify fresh opening-range events from CLOSED 5m candles only.

    BREAKOUT: first candle closes outside a buffered 09:15–09:30 range.
    FAKEOUT: an inside-range candle sweeps above/below range on its wick,
             rejects the level, and finishes back inside (no prior close out).
    TRAP: an outside CLOSE was recorded on the preceding 1–3 candles, and
          price closes back inside on the opposite side of that boundary.
          The trade points opposite to those caught in the failed breakout.
    All three are mutually exclusive for a given closed bar.
    """
    opening=[b for b in closed if b.time.time() in
             (dt.time(9,15),dt.time(9,20),dt.time(9,25))]
    if [b.time.time() for b in opening] != [dt.time(9,15),dt.time(9,20),dt.time(9,25)]:
        return None
    ceiling=max(b.high for b in opening)
    floor=min(b.low for b in opening)
    width=ceiling-floor
    if width<=0 or len(closed)<4:
        return None
    # Require a small, precommitted breakout clearance to avoid comparing
    # merely rounded equal-price touches with fully confirmed breakouts.
    buffer=max(.05*width,1e-7)
    last=closed[-1]
    prev=closed[-2]
    inside=(floor<=last.close<=ceiling)
    if inside:
        # A previously confirmed breakout can trap those entering after it.
        # Only recent 1–3 outside closes qualify; much later return-to-range
        # after a trend is not labeled a trap.
        for old_side,boundary,reverse in (('UP',ceiling,'BEAR'),('DOWN',floor,'BULL')):
            if old_side=='UP' and not (prev.close>ceiling+buffer and last.close<ceiling-buffer):
                continue
            if old_side=='DOWN' and not (prev.close<floor-buffer and last.close>floor+buffer):
                continue
            episode=[]
            for old in reversed(closed[:-1]):
                if (old.close>ceiling+buffer if old_side=='UP' else old.close<floor-buffer):
                    episode.append(old)
                else:
                    break
            if not 1<=len(episode)<=3:
                continue
            if old_side=='UP' and not last.close<prev.close:continue
            if old_side=='DOWN' and not last.close>prev.close:continue
            peak=(max(b.high for b in episode+[last]) if old_side=='UP'
                  else min(b.low for b in episode+[last]))
            return {'strategy':'OPENING_RANGE_TRAP','direction':reverse,
                    'strength':3,'range_pattern':'TRAP',
                    'failed_breakout_side':old_side,'sweep_extreme':peak,
                    'breakout_level':boundary,'bars_outside':len(episode),
                    'confirmation':'PRIOR_CLOSE_OUTSIDE_THEN_CLOSE_INSIDE'}
        # A wick sweep, with no breakout close, is a simpler fakeout.
        # A candle sweeping both levels is ambiguous and is ignored.
        high_sweep=last.high>ceiling+buffer and last.close<ceiling and last.close>=floor
        low_sweep=last.low<floor-buffer and last.close>floor and last.close<=ceiling
        if high_sweep != low_sweep:
            candle_range=last.high-last.low
            if candle_range>0:
                if (high_sweep and prev.close<=ceiling and
                    prev.high<=ceiling+buffer and last.close<=last.open and
                    (last.high-max(last.open,last.close))/candle_range>=.20):
                    return {'strategy':'OPENING_RANGE_FAKEOUT','direction':'BEAR',
                            'strength':2,'range_pattern':'FAKEOUT',
                            'failed_breakout_side':'UP','sweep_extreme':last.high,
                            'breakout_level':ceiling,
                            'confirmation':'UPPER_WICK_SWEEP_CLOSES_BACK_INSIDE'}
                if (low_sweep and prev.close>=floor and
                    prev.low>=floor-buffer and last.close>=last.open and
                    (min(last.open,last.close)-last.low)/candle_range>=.20):
                    return {'strategy':'OPENING_RANGE_FAKEOUT','direction':'BULL',
                            'strength':2,'range_pattern':'FAKEOUT',
                            'failed_breakout_side':'DOWN','sweep_extreme':last.low,
                            'breakout_level':floor,
                            'confirmation':'LOWER_WICK_SWEEP_CLOSES_BACK_INSIDE'}
    # At least one fully CLOSED candle must cross the buffered range boundary;
    # do not trade an unconfirmed intrabar breakout.
    if last.close>ceiling+buffer and prev.close<=ceiling+buffer:
        return {'strategy':'OPENING_RANGE_BREAKOUT','direction':'BULL',
                'strength':2,'range_pattern':'BREAKOUT',
                'breakout_level':ceiling,'confirmation':'CLOSED_ABOVE_OR_HIGH'}
    if last.close<floor-buffer and prev.close>=floor-buffer:
        return {'strategy':'OPENING_RANGE_BREAKOUT','direction':'BEAR',
                'strength':2,'range_pattern':'BREAKOUT',
                'breakout_level':floor,'confirmation':'CLOSED_BELOW_OR_LOW'}
    return None


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
    event=_opening_range_signal(closed,end)
    if event:
        return {**event,'bar':last.time.isoformat(),
                'confirmed_at':end.isoformat()}
    previous = closed[-2]
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


def _fees_credit_breakdown(sell_bid,buy_ask,short_exit,long_exit,qty,exchange):
    # Both legs have a buy and a sell, hence four hypothetical executions.
    short_fees=option_fees(short_exit,sell_bid,qty,exchange,'UPSTOX')
    hedge_fees=option_fees(buy_ask,long_exit,qty,exchange,'UPSTOX')
    fields=('brokerage','stt','exchange_transaction_charge','gst',
            'sebi','ipft','stamp_duty')
    total={key:money(short_fees.get(key,0)+hedge_fees.get(key,0)) for key in fields}
    total['total']=money(short_fees['total']+hedge_fees['total'])
    total['broker_profile']='UPSTOX'
    return total


def _fees_credit_round_trip(sell_bid,buy_ask,short_exit,long_exit,qty,exchange):
    return _fees_credit_breakdown(sell_bid,buy_ask,short_exit,long_exit,qty,exchange)['total']


def select_credit_spread(records,chain,market,direction,spot,today,settings,expiry=None,
                         lots=1,max_spread_pct=2,remaining_daily_loss=None,
                         min_reward_risk=0.0,index_stop_plan=None):
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
    cap=min(float(settings['max_loss_per_trade_inr']),
            float(remaining_daily_loss) if remaining_daily_loss is not None
            else float(settings['max_loss_per_trade_inr']))
    if cap<=0:
        raise UpstoxError('Daily paper loss budget exhausted')
    if min_reward_risk<0:
        raise UpstoxError('Minimum credit spread reward:risk cannot be negative')
    allocation=float(settings['capital_inr'])*float(settings['max_allocation_fraction'])
    ranked=[]
    blocked={'expiry_risk_above_cap':0,'credit_stop_above_cap':0,
             'target_profit_or_rr_too_low':0,'missing_valid_wing_or_credit':0}
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
                blocked['missing_valid_wing_or_credit']+=1
                continue
            credit=short['leg']['bid']-hedge['leg']['ask']
            if credit<=0:
                blocked['missing_valid_wing_or_credit']+=1
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
                blocked['expiry_risk_above_cap']+=1
                continue
            target_debit=max(.01,credit*.4)
            stop_debit=credit*2
            hedge_bid=hedge['leg']['bid']
            target_fees=_fees_credit_round_trip(short['leg']['bid'],hedge['leg']['ask'],
                                                max(.01,target_debit+hedge_bid),hedge_bid,qty,exchange)
            stop_fees=_fees_credit_round_trip(short['leg']['bid'],hedge['leg']['ask'],
                                              max(.01,stop_debit+hedge_bid),hedge_bid,qty,exchange)
            target_net=money((credit-target_debit)*qty-target_fees)
            stop_net_loss=money((stop_debit-credit)*qty+stop_fees)
            # The planned close debit can exceed theoretical expiry payoff:
            # BOTH losses must fit the same hard *modeled* INR risk cap.
            if stop_net_loss>cap:
                blocked['credit_stop_above_cap']+=1
                continue
            planned_rr=(target_net/stop_net_loss) if stop_net_loss>0 else 0
            if min_reward_risk>0 and (target_net<=0 or planned_rr<min_reward_risk):
                blocked['target_profit_or_rr_too_low']+=1
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
                            'estimated_target_net_profit':target_net,
                            'estimated_stop_net_loss':stop_net_loss,
                            'net_reward_risk_at_credit_stop':round(planned_rr,3),
                            'minimum_net_reward_risk':min_reward_risk,
                            'index_stop_plan':index_stop_plan,
                            'margin_not_verified':True,'executable_fill_not_guaranteed':True,
                            'source':'UPSTOX_REST_OPTION_CHAIN_PAPER'}))
    if not ranked:
        counts=', '.join(f'{key}={value}' for key,value in blocked.items() if value)
        raise UpstoxError('No defined-risk credit spread passed. '
                          'Matching liquid OTM legs='+str(len(rows))+
                          '; cap=₹'+f'{cap:.2f}'+
                          '; rejections: '+(counts or 'no matching executable hedge pair'))
    return min(ranked,key=lambda e:e[:3])[3]


def spread_mark(position,chain,market,now,stop_multiplier=2,target_fraction=.4,
                index_close=None):
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
    fee_details=_fees_credit_breakdown(position['short_bid'],position['long_ask'],
                                  short['ask'],long['bid'],position['quantity'],exchange)
    fees=fee_details['total']
    net=money((position['credit_per_unit']-exit_debit)*position['quantity']-fees)
    tm=now.astimezone(IST).time()
    cutoff=dt.time(14,45) if dt.date.fromisoformat(position['expiry'])==now.date() else dt.time(15,15)
    stop_plan=position.get('index_stop_plan') or {}
    stop_level=stop_plan.get('index_stop')
    index_invalid=(index_close is not None and stop_level is not None and
                   ((position['direction']=='BULL' and index_close<=stop_level) or
                    (position['direction']=='BEAR' and index_close>=stop_level)))
    reason=('TIME_EXIT' if tm>=cutoff else
            'INDEX_STOP' if index_invalid else
            'CREDIT_STOP' if exit_debit>=position['credit_per_unit']*stop_multiplier else
            'CREDIT_TARGET' if (exit_debit<=position['credit_per_unit']*target_fraction and net>0) else None)
    return {'reason':reason,'net_pnl':net,'fees':fees,'fees_breakdown':fee_details,
            'exit_debit':money(exit_debit),'bid_long':long['bid'],
            'ask_short':short['ask'],'source':'INDICATIVE_REST_QUOTES_NOT_EXCHANGE_FILLS'}
