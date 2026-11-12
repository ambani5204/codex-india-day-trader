"""Fail-closed risk planning for Indian index option PAPER buys.

The original US exit -> budget -> risk workflow is adapted to *actual*
NFO/BFO full lots and fee-aware price plans. A spot-index ATR or opening-
range stop is translated to a HYPOTHETICAL option-price move via first-order
delta sensitivity; this is NOT a guaranteed option stop or a broker order.
All functions are pure and use only timestamped, closed bars and real quote
fields supplied by the caller. No hidden network access.
"""
from __future__ import annotations

import datetime as dt
import math
from statistics import mean, median
from .core import IST
from .paper_sim import money, option_fees
from .upstox import UpstoxError, INDICES, EXCHANGES, normalize_expiry


def adaptive_paper_risk(settings, realized_net=0.0, realized_losses=0.0):
    """One percent of remaining paper equity, capped by DAILY remaining loss.

    Advanced mode only; the original fixed-INR configuration and ORB runner
    stay untouched. Percent is configurable from 0.10% to 1.00%, not unbounded.
    A profitable trade does NOT restore previously lost daily loss allowance.
    """
    try:
        capital=float(settings['capital_inr'])
        daily_limit=float(settings['max_daily_loss_inr'])
        percent=float(settings.get('advanced_risk_percent',1.0))
        pnl=float(realized_net)
        losses=float(realized_losses)
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        raise UpstoxError('Invalid adaptive risk settings') from exc
    if not all(math.isfinite(v) for v in (capital,daily_limit,percent,pnl,losses)):
        raise UpstoxError('Risk settings must be finite')
    if capital<=0 or daily_limit<=0 or not .1<=percent<=1.0 or losses<0:
        raise UpstoxError('Advanced risk must be 0.1–1.0% with positive capital and daily budget')
    # Paper equity shrinks with a losing session; the daily loss limit never
    # increases after profitable trades, even if paper equity is higher.
    equity=max(0.0,capital+pnl)
    remaining=max(0.0,daily_limit-losses)
    raw=money(equity*percent/100.0)
    cap=money(min(raw,remaining))
    if cap<=0 or pnl<=-daily_limit:
        raise UpstoxError('No remaining advanced paper trade risk allowance')
    return {'mode':'ADVANCED_PERCENT_EQUITY',
            'risk_percent':percent,'paper_equity_inr':money(equity),
            'unconstrained_trade_risk_inr':raw,
            'remaining_daily_loss_inr':money(remaining),
            'trade_risk_cap_inr':cap}


def _completed_today(bars, now):
    now=now.astimezone(IST)
    completed=sorted((b for b in bars if b.time.date()==now.date()
                      and b.time+dt.timedelta(minutes=5)<=now),
                     key=lambda b:b.time)
    # Reject missing candles: a false low ATR can make unsafe tight stops.
    if any(b.time-a.time!=dt.timedelta(minutes=5) for a,b in zip(completed,completed[1:])):
        raise UpstoxError('Incomplete five-minute index history: cannot plan ATR stop')
    return completed


def atr_5m(bars, period=14):
    """Wilder's ATR from chronologically sorted, fully CLOSED 5-minute bars."""
    if period<1 or len(bars)<period+1:
        raise UpstoxError(f'ATR({period}) requires at least {period+1} closed 5m bars')
    ranges=[]
    for prev,current in zip(bars,bars[1:]):
        ranges.append(max(current.high-current.low,abs(current.high-prev.close),
                          abs(current.low-prev.close)))
    # Standard Wilder smoothing seeded using the earliest 14 true ranges.
    value=sum(ranges[:period])/period
    for tr in ranges[period:]:
        value=(value*(period-1)+tr)/period
    if not math.isfinite(value) or value<=0:
        raise UpstoxError('ATR is zero or invalid; paper entry blocked')
    return value


def index_stop_plan(bars,signal,spot,now,atr_multiplier=1.5):
    """Strategy-specific invalidation/target from genuinely closed index bars.

    ORB: breakout boundary with a volatility buffer; when the entire breakout
    candle sits above/below the opening range, use that candle's extreme
    (momentum-candle invalidation). ATR is NOT invented at 09:35.

    EMA 8/21: last six bars' swing extremum with 0.2 ATR buffer, rejecting
    extended entries rather than arbitrarily tightening the stop.

    Mean reversion: last three bars' extreme with 0.2 ATR buffer; target
    the preceding 20-bar mean (same lookback as the entry signal).
    """
    if not math.isfinite(spot) or spot<=0 or signal.get('direction') not in {'BULL','BEAR'}:
        raise UpstoxError('Invalid spot/direction for index stop')
    completed=_completed_today(bars,now)
    if not completed:
        raise UpstoxError('No closed candles for stop calculation')
    if not math.isfinite(atr_multiplier) or atr_multiplier<=0:
        raise UpstoxError('ATR multiplier must be positive')
    side=signal['direction']
    strategy=signal.get('strategy')
    last=completed[-1]
    if strategy=='OPENING_RANGE_BREAKOUT':
        opening=[b for b in completed if dt.time(9,15)<=b.time.time()<dt.time(9,30)]
        if [b.time.time() for b in opening]!=[dt.time(9,15),dt.time(9,20),dt.time(9,25)]:
            raise UpstoxError('Opening range incomplete; cannot plan structural stop')
        high=max(b.high for b in opening)
        low=min(b.low for b in opening)
        width=high-low
        if width<=0:
            raise UpstoxError('Opening range has no valid width')
        typical=median(b.high-b.low for b in opening)
        buffer=max(.15*width,.25*typical)
        if side=='BULL':
            if spot<=high:
                raise UpstoxError('ORB bullish close no longer above opening high')
            if last.low>high+buffer:
                stop=last.low-buffer
                basis='ORB_BREAKOUT_CANDLE_LOW'
            else:
                stop=high-buffer
                basis='ORB_OPENING_HIGH_RETEST'
        else:
            if spot>=low:
                raise UpstoxError('ORB bearish close no longer below opening low')
            if last.high<low-buffer:
                stop=last.high+buffer
                basis='ORB_BREAKOUT_CANDLE_HIGH'
            else:
                stop=low+buffer
                basis='ORB_OPENING_LOW_RETEST'
        atr=atr_5m(completed) if len(completed)>=15 else None
        # The original US exit skill uses a pre-committed 2R target by default.
        # It is a hypothetical projection, not an expected market move.
        target_basis='ORB_2R_PROJECTION'
        target=None
    elif strategy=='EMA_8_21_CROSS':
        atr=atr_5m(completed)
        recent=completed[-6:]
        buffer=.2*atr
        stop=(min(b.low for b in recent)-buffer if side=='BULL' else
              max(b.high for b in recent)+buffer)
        basis='EMA_6_BAR_SWING_WITH_ATR_BUFFER'
        target_basis='EMA_2R_TREND_PROJECTION'
        target=None
    elif strategy=='MEAN_REVERSION':
        atr=atr_5m(completed)
        recent=completed[-3:]
        buffer=.2*atr
        stop=(min(b.low for b in recent)-buffer if side=='BULL' else
              max(b.high for b in recent)+buffer)
        basis='MEAN_REVERSION_RECENT_EXTREME_WITH_ATR_BUFFER'
        # Reference excludes the reversal bar, matching intraday_signal.
        if len(completed)<21:
            raise UpstoxError('Mean reversion needs 20 prior closed bars')
        target=mean(b.close for b in completed[-21:-1])
        target_basis='MEAN_REVERSION_20_BAR_MEAN'
    else:
        raise UpstoxError('Unknown strategy cannot choose a stop or target')
    gap=spot-stop if side=='BULL' else stop-spot
    if not math.isfinite(gap) or gap<=0 or stop<=0:
        raise UpstoxError('Strategy invalidation stop is on the wrong side')
    if strategy=='EMA_8_21_CROSS' and gap>2.5*atr:
        raise UpstoxError('EMA entry overextended from real swing (>2.5 ATR); skip rather than tighten stop')
    if target is None:
        target=(spot+2*gap) if side=='BULL' else (spot-2*gap)
    reward=target-spot if side=='BULL' else spot-target
    if not math.isfinite(reward) or reward<=0 or target<=0:
        raise UpstoxError('No valid favorable structural target for the setup')
    return {'index_spot':money(spot),'index_stop':money(stop),
            'index_risk_points':money(gap),'index_target':money(target),
            'index_reward_points':money(reward),
            'index_gross_reward_risk':round(reward/gap,3),
            'basis':basis,'target_basis':target_basis,
            'atr_5m':money(atr) if atr is not None else None,
            'warning':'Index invalidation is checked only on closed candles; options Greeks change; fill stops and targets are not guaranteed'}


def _evaluate_one_lot(ask,bid,delta,lot_size,exchange,settings,index_plan,
                      target_pct,min_rr,slippage_bps=5):
    if any(not math.isfinite(x) for x in (ask,bid,delta,slippage_bps)):
        raise UpstoxError('Invalid option price or delta')
    if not 0<bid<=ask or not 0<abs(delta)<1 or lot_size<1:
        raise UpstoxError('Bad option bid/ask/delta/lot')
    if target_pct<=0 or min_rr<=0 or slippage_bps<0:
        raise UpstoxError('Invalid reward/risk parameters')
    quantity=int(lot_size)
    entry=money(ask*(1+slippage_bps/10000))
    # Stop triggers on *bid*, while entry happens on *ask*, so entry
    # spread is part of the risk (no falsely cheap mid-price fills).
    index_gap=float(index_plan['index_risk_points'])
    stop=money(bid-abs(delta)*index_gap)
    # Base the option exit on the chart setup's STRUCTURAL target. We can
    # map first-order delta only; IV/theta/gamma can make actual option
    # premiums differ. Do not silently fall back to an arbitrary 30% target
    # if the setup has no favorable index target.
    if 'index_reward_points' in index_plan:
        gain=float(index_plan['index_reward_points'])
        if not math.isfinite(gain) or gain<=0:
            raise UpstoxError('Invalid chart-based target distance')
        target=money(bid+abs(delta)*gain)
    else:
        # Compatibility for explicit standalone/manual pre-2026 test plans;
        # the advanced trading worker always supplies index_reward_points.
        target=money(ask*(1+target_pct/100))
    if stop<=0 or stop>=bid or stop>=entry or target<=entry:
        raise UpstoxError('Delta-mapped option stop outside valid premium range')
    estimated_stop_exit=money(stop*(1-slippage_bps/10000))
    est_loss=(entry-estimated_stop_exit)*quantity+option_fees(entry,estimated_stop_exit,quantity,exchange,'UPSTOX')['total']
    est_target_exit=money(target*(1-slippage_bps/10000))
    est_reward=(est_target_exit-entry)*quantity-option_fees(entry,est_target_exit,quantity,exchange,'UPSTOX')['total']
    if est_reward<=0:
        raise UpstoxError('Target loses money after option charges')
    ratio=est_reward/est_loss if est_loss>0 else 0
    if ratio<min_rr:
        raise UpstoxError(f'Net reward:risk {ratio:.2f} below minimum {min_rr:.2f} after fees')
    if est_loss>float(settings['max_loss_per_trade_inr']):
        raise UpstoxError(f'One option lot costs ₹{est_loss:.2f} at modeled stop, exceeds trade cap')
    return {'entry':entry,'stop_bid':stop,'target_bid':target,
            'loss_per_lot':money(est_loss),'target_reward_per_lot':money(est_reward),
            'net_reward_risk':round(ratio,3),
            'target_basis':('INDEX_STRUCTURE_DELTA' if 'index_reward_points' in index_plan
                            else 'EXPLICIT_MANUAL_PREMIUM_TARGET'),
            'stop_pct_implied':round(100*(entry-stop)/entry,3),
            'target_pct_implied':round(100*(target-entry)/entry,3)}


def size_long_option(ask,bid,delta,lot_size,exchange,settings,index_plan,
                     target_pct=30,min_rr=1.5,max_lots=3,
                     remaining_daily_loss=None,slippage_bps=5):
    """Only whole lots; no change of stop or risk limit to force a trade."""
    if max_lots<1 or int(max_lots)!=max_lots:
        raise UpstoxError('max_lots must be a positive whole number')
    planned=_evaluate_one_lot(ask,bid,delta,lot_size,exchange,settings,index_plan,
                              target_pct,min_rr,slippage_bps)
    cap=min(float(settings['max_loss_per_trade_inr']),
            float(remaining_daily_loss) if remaining_daily_loss is not None
            else float(settings['max_loss_per_trade_inr']))
    allocation=float(settings['capital_inr'])*float(settings['max_allocation_fraction'])
    if cap<=0 or allocation<=0:
        raise UpstoxError('Trade/daily risk budget depleted')
    for lots in range(min(int(max_lots),int(allocation/(planned['entry']*lot_size))),0,-1):
        qty=lots*int(lot_size)
        stop_bid=planned['stop_bid']; entry=planned['entry']; target_bid=planned['target_bid']
        stop_exit=money(stop_bid*(1-slippage_bps/10000))
        target_exit=money(target_bid*(1-slippage_bps/10000))
        loss=money((entry-stop_exit)*qty+
                   option_fees(entry,stop_exit,qty,exchange,'UPSTOX')['total'])
        reward=money((target_exit-entry)*qty-
                     option_fees(entry,target_exit,qty,exchange,'UPSTOX')['total'])
        if loss<=cap and reward>0 and reward/loss>=min_rr:
            return {**planned,'quantity':qty,'lots':lots,
                    'estimated_stop_loss_including_charges':loss,
                    'estimated_target_net_profit':reward,
                    'net_reward_risk':round(reward/loss,3),
                    'premium_outlay_at_ask':money(ask*qty),
                    'risk_cap_inr':money(cap)}
    raise UpstoxError('Cannot fit even one full option lot within remaining INR risk/capital budget')


def select_long_risk_managed(records,chain,market,direction,spot,today,settings,
                             index_plan,expiry,target_pct=30,min_rr=1.5,
                             max_lots=3,remaining_daily_loss=None):
    """Find valid live-delta long CE/PE and *plan* stop and size before entry.

    Unlike the legacy ORB selector, rejection is based on a structural/ATR
    stop and net fees, not a fixed 15% premium stop. Only current master
    contracts and specified non-expiry-day expiration are supported.
    """
    if market not in INDICES or direction not in ('BULL','BEAR'):
        raise UpstoxError('Unsupported paper market or direction')
    if not (settings.get('paper') and not settings.get('allow_live_orders')):
        raise UpstoxError('Risk-managed option selection is paper-only')
    kind='CE' if direction=='BULL' else 'PE'
    seg,exchange=EXCHANGES[market]
    expiry_day=dt.date.fromisoformat(expiry)
    if expiry_day<=today:
        raise UpstoxError('Long option expiry-day entries prohibited')
    valid={}
    for row in records:
        if row.get('segment')!=seg or row.get('instrument_type')!=kind:continue
        underlying=str(row.get('underlying_symbol','')).upper()
        if row.get('underlying_key')!=INDICES[market] and underlying not in (
            {'NIFTY','NIFTY 50'} if market=='NIFTY' else {'SENSEX'}):
            continue
        try:
            if normalize_expiry(row['expiry'])==expiry_day:
                valid[row['instrument_key']]=row
        except (ValueError,KeyError,TypeError,OverflowError):
            continue
    options=[]
    reasons={}
    for strike_row in chain:
        try:
            if dt.date.fromisoformat(str(strike_row['expiry']))!=expiry_day:continue
            entry=strike_row.get('call_options' if kind=='CE' else 'put_options') or {}
            key=entry['instrument_key']
            if key not in valid:continue
            bid=float(entry['market_data']['bid_price'])
            ask=float(entry['market_data']['ask_price'])
            bid_qty=int(entry['market_data']['bid_qty'])
            ask_qty=int(entry['market_data']['ask_qty'])
            delta=float(entry['option_greeks']['delta'])
            lot=int(valid[key]['lot_size'])
            strike=float(valid[key]['strike_price'])
            if not (0.4<=abs(delta)<=0.65 and (delta>0 if kind=='CE' else delta<0)):
                continue
            if not (0<bid<=ask and 200*(ask-bid)/(ask+bid)<=2
                    and bid_qty>=lot and ask_qty>=lot):
                continue
            # Size down to visible executable depth instead of rejecting
            # an otherwise valid smaller whole-lot position.
            depth_lots=min(int(max_lots),bid_qty//lot,ask_qty//lot)
            plan=size_long_option(ask,bid,delta,lot,exchange,settings,index_plan,
                     target_pct,min_rr,depth_lots,remaining_daily_loss)
            options.append((abs(abs(delta)-.5),abs(strike-spot),-plan['net_reward_risk'],
                            {'instrument_key':key,'expiry':expiry,'strike':strike,
                             'lot_size':lot,'market':market,'exchange':exchange,
                             'option_type':kind,
                             'symbol':f'{exchange}:{market}_{strike:g}_{expiry}_{kind}',
                             'delta':delta,'quoted_bid':bid,'quoted_ask':ask,
                             'quoted_bid_qty':bid_qty,'quoted_ask_qty':ask_qty,
                             'index_stop_plan':index_plan,'risk_plan':plan,
                             'selection':'ATR_ORB_NET_RISK_LOT_SIZED'}))
        except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError,UpstoxError) as exc:
            reason=str(exc).split(':')[0][:110]
            reasons[reason]=reasons.get(reason,0)+1
    if not options:
        details=', '.join(f'{k}: {v}' for k,v in sorted(reasons.items())) or 'no valid delta/liquidity candidate'
        raise UpstoxError('No risk-managed full-lot long option passed: '+details)
    return min(options,key=lambda x:x[:3])[3]
