"""Deterministic, cost-aware FORWARD PAPER simulator. Never places orders.

Quotes must have executable bid/ask depth; an index LTP is NOT an option fill.
Fee schedule: Zerodha charges page as observed 2026-11-11, effective 2026-04-01.
Round STT per transaction to nearest rupee (approximation; reconcile contract notes).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import csv
import json
import math
from .core import IST, parse_time, is_index

FEE_EFFECTIVE = '2026-04-01'
FEE_SOURCE = 'https://zerodha.com/charges/'


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def stt_rupee(value):
    return float(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def option_fees(buy_price, sell_price, quantity, exchange, broker="ZERODHA"):
    """NFO/BFO index long-option *buy then sell*, cash-settled intraday only.

    Brokerage per executed order, STT on sell premium, no exercise/auto square-off.
    Fees are estimates; a broker contract note is authoritative.
    """
    if exchange not in {'NFO','BFO'} or broker not in {'ZERODHA','UPSTOX'}:
        raise ValueError('Fees support NFO/BFO long options, basic UPSTOX or ZERODHA only')
    if min(buy_price,sell_price,quantity)<=0 or int(quantity)!=quantity:
        raise ValueError('Prices and integral quantity must be positive')
    buy_turnover=buy_price*quantity
    sell_turnover=sell_price*quantity
    total_turnover=buy_turnover+sell_turnover
    bse=exchange=='BFO'
    exchange_rate=0.000325 if bse else 0.0003553   # BSE SENSEX/BANKEX; NSE equity options
    brokerage=40.0
    exchange_charge=total_turnover*exchange_rate
    sebi=total_turnover * 10 / 10000000
    # Upstox publishes an additional NSE investor protection trust (IPFT) premium levy.
    # Fee values remain estimates; reconcile against contract note when available.
    ipft=(total_turnover*0.5/100000) if (broker=='UPSTOX' and not bse) else 0.0
    gst=(brokerage+exchange_charge+sebi+ipft)*0.18
    stamp=buy_turnover*0.00003
    stt=stt_rupee(sell_turnover*0.0015)
    subtotal=brokerage+exchange_charge+sebi+gst+stamp+stt+ipft
    return {'brokerage':money(brokerage),'stt':money(stt),
            'exchange_transaction_charge':money(exchange_charge),'sebi':money(sebi),
            'gst':money(gst),'stamp_duty':money(stamp),'ipft':money(ipft), 'other':0.0, 'broker_profile':broker,
            'total':money(subtotal), 'fee_effective_from':FEE_EFFECTIVE,
            'fee_source':'https://upstox.com/brokerage-charges/' if broker=='UPSTOX' else FEE_SOURCE,
            'exclusions':'Exercise/expiry settlement, penalties, auto square-off, data subscription, income tax, broker-specific fees'}


def breakeven_sell(buy_price,quantity,exchange,broker="ZERODHA"):
    lo,hi=buy_price,buy_price*3+100
    for _ in range(60):
        mid=(lo+hi)/2
        net=(mid-buy_price)*quantity-option_fees(buy_price,mid,quantity,exchange,broker)['total']
        if net>=0:hi=mid
        else:lo=mid
    return money(hi)


@dataclass(frozen=True)
class Quote:
    timestamp: datetime
    bid: float
    ask: float
    bid_qty: int
    ask_qty: int
    last: float = 0.0
    bid_levels: tuple = () # tuple of (price,quantity)
    ask_levels: tuple = ()

    def __post_init__(self):
        if self.timestamp.tzinfo is None:raise ValueError('Quote timestamp needs timezone')
        if not (0 < self.bid <= self.ask): raise ValueError('Bad/missing bid ask prices')
        if self.bid_qty<0 or self.ask_qty<0:raise ValueError('Bad depth quantities')

    @classmethod
    def from_kite(cls, data):
        depth=data.get('depth') or {}
        def levels(side):
            return tuple((float(x['price']),int(x['quantity'])) for x in (depth.get(side) or [])
                         if float(x.get('price',0))>0 and int(x.get('quantity',0))>0)
        b,a=levels('buy'),levels('sell')
        if not b or not a:raise ValueError('Kite quote missing positive best bid/ask depth; paper fill blocked')
        timestamp=data.get('timestamp')
        if not timestamp:raise ValueError('Missing exchange timestamp; cannot verify freshness')
        return cls(parse_time(timestamp),b[0][0],a[0][0],b[0][1],a[0][1],
                   float(data.get('last_price') or 0),b,a)

    @classmethod
    def from_csv(cls, row):
        return cls(parse_time(row['timestamp']),float(row['bid']),float(row['ask']),
                   int(row['bid_qty']),int(row['ask_qty']),float(row.get('last') or 0))


def realistic_fill(quote, direction, quantity, slippage_bps=5.0):
    """Walk visible levels, add adverse slippage, decline insufficient book liquidity."""
    if direction not in {'BUY','SELL'} or quantity<=0:raise ValueError('Invalid fill request')
    levels=quote.ask_levels if direction=='BUY' else quote.bid_levels
    if not levels:
        levels=((quote.ask,quote.ask_qty),) if direction=='BUY' else ((quote.bid,quote.bid_qty),)
    qty_left=quantity
    paid=0.0
    for price,avail in levels:
        take=min(qty_left,int(avail))
        paid+=take*price
        qty_left-=take
        if qty_left==0:break
    if qty_left>0:return None
    px=paid/quantity
    px*=1+(slippage_bps/10000)*(1 if direction=='BUY' else -1)
    if px<=0:raise ValueError('Invalid slippage')
    return money(px) # approximated fill; actual exchange tick rounding can differ


class PaperEngine:
    """One buy-to-open index option and sell-to-close, signal never sends orders."""
    def __init__(self, symbol, quantity, capital, max_trade_loss, exchange=None,
                 stop_pct=15.0,target_pct=30.0,max_spread_pct=2.0,slippage_bps=5.0,
                 latency_ms=750, max_allocation_fraction=0.25, fee_profile="ZERODHA",
                 flat_by=time(15,20), planned_stop=None, planned_target=None,
                 min_net_reward_risk=None, remaining_daily_loss=None):

        self.symbol=symbol
        if fee_profile not in {'ZERODHA','UPSTOX'}:raise ValueError('Unsupported brokerage profile')
        self.fee_profile=fee_profile
        self.exchange=exchange or symbol.split(':',1)[0]
        if is_index(symbol) or self.exchange not in {'NFO','BFO'} or not symbol.endswith(('CE','PE')):
            raise ValueError('Only real NFO/BFO CE/PE contracts can be simulated. Never order an index')
        if not (quantity>0 and int(quantity)==quantity and capital>0 and max_trade_loss>0):
            raise ValueError('Bad quantity/capital/risk')
        if not (0<stop_pct<100 and target_pct>0 and max_spread_pct>0 and slippage_bps>=0 and latency_ms>=0):
            raise ValueError('Bad stops/targets/slippage')
        self.quantity=int(quantity); self.capital=capital; self.max_trade_loss=max_trade_loss
        self.max_allocation_fraction=max_allocation_fraction
        self.stop_pct=stop_pct;self.target_pct=target_pct
        self.max_spread_pct=max_spread_pct; self.slippage_bps=slippage_bps
        self.latency_ms=latency_ms
        self.flat_by=flat_by
        self.planned_stop=planned_stop
        self.planned_target=planned_target
        self.min_net_reward_risk=min_net_reward_risk
        self.remaining_daily_loss=remaining_daily_loss
        self.position=None;self.pending=None;self.events=[];self.last_quote=None

    def process(self, quote, signal=False, reason='MANUAL', now=None, max_age_seconds=None):
        if max_age_seconds is not None:
            if now is None:raise ValueError('Clock required for freshness validation')
            age=(now.astimezone(IST)-quote.timestamp.astimezone(IST)).total_seconds()
            if age< -3 or age>max_age_seconds:
                return self._event({'event':'QUOTE_REJECTED','timestamp':quote.timestamp.isoformat(),
                                    'reason':'STALE_OR_FUTURE_QUOTE','age_seconds':round(age,2)})
        self.last_quote=quote
        if self.pending and quote.timestamp>=self.pending['due']:
            pending=self.pending;self.pending=None
            return self._fill(quote,pending['action'],pending['reason'])
        if self.pending:return None
        if self.position is not None:
            reason=None
            if quote.bid<=self.position['stop_price']:reason='STOP'
            elif quote.bid>=self.position['target_price']:reason='TARGET'
            elif quote.timestamp.astimezone(IST).time()>=self.flat_by:reason='TIME_EXIT'
            if reason:
                self.pending={'action':'SELL','reason':reason,
                              'due':quote.timestamp+timedelta(milliseconds=self.latency_ms)}
                return self._event({'event':'EXIT_SIGNAL','timestamp':quote.timestamp.isoformat(),
                                    'reason':reason,'bid_at_signal':quote.bid})
            return None
        if signal:
            if not time(9,15) <= quote.timestamp.astimezone(IST).time() < time(15,10):
                return self._event({'event':'ENTRY_BLOCKED','reason':'OUTSIDE_ENTRY_WINDOW','timestamp':quote.timestamp.isoformat()})
            self.pending={'action':'BUY','reason':reason,
                          'due':quote.timestamp+timedelta(milliseconds=self.latency_ms)}
            return self._event({'event':'ENTRY_SIGNAL','timestamp':quote.timestamp.isoformat(),
                                'reason':reason,'ask_at_signal':quote.ask})
        return None

    def _event(self,event):
        event['symbol']=self.symbol
        self.events.append(event)
        return event

    def _fill(self, quote, direction, reason):
        spread_pct=100*(quote.ask-quote.bid)/((quote.ask+quote.bid)/2)
        if spread_pct>self.max_spread_pct:
            ev='ENTRY_REJECTED' if direction=='BUY' else 'EXIT_UNFILLED'
            return self._event({'event':ev,'reason':'WIDE_SPREAD','spread_pct':round(spread_pct,3),
                                'timestamp':quote.timestamp.isoformat()})
        px=realistic_fill(quote,direction,self.quantity,self.slippage_bps)
        if px is None:
            ev='ENTRY_REJECTED' if direction=='BUY' else 'EXIT_UNFILLED'
            return self._event({'event':ev,'reason':'INSUFFICIENT_VISIBLE_DEPTH',
                                'timestamp':quote.timestamp.isoformat()})
        if direction=='BUY':
            stop=money(self.planned_stop) if self.planned_stop is not None else money(px*(1-self.stop_pct/100))
            target=money(self.planned_target) if self.planned_target is not None else money(px*(1+self.target_pct/100))
            if stop<=0 or stop>=px or target<=px:
                return self._event({'event':'ENTRY_REJECTED','reason':'STOP_OR_TARGET_INVALID_AFTER_FILL',
                                    'timestamp':quote.timestamp.isoformat()})
            # Recalculate after the delayed fill: neither a worse fill nor
            # additional fees may silently exceed the user risk budget.
            stop_fees=option_fees(px,stop,self.quantity,self.exchange,self.fee_profile)['total']
            expected_loss=(px-stop)*self.quantity+stop_fees
            effective_cap=min(self.max_trade_loss,self.remaining_daily_loss
                              if self.remaining_daily_loss is not None else self.max_trade_loss)
            if px*self.quantity > self.capital*self.max_allocation_fraction or expected_loss>effective_cap:
                return self._event({'event':'ENTRY_REJECTED','reason':'CAPITAL_OR_MAX_LOSS_LIMIT',
                                    'premium_outlay':money(px*self.quantity),'stop_loss_with_estimated_fees':money(expected_loss),
                                    'risk_cap':money(effective_cap),'timestamp':quote.timestamp.isoformat()})
            target_fees=option_fees(px,target,self.quantity,self.exchange,self.fee_profile)['total']
            reward=(target-px)*self.quantity-target_fees
            ratio=reward/expected_loss if expected_loss>0 else 0.0
            if self.min_net_reward_risk is not None and (reward<=0 or ratio<self.min_net_reward_risk):
                return self._event({'event':'ENTRY_REJECTED','reason':'NET_REWARD_RISK_TOO_LOW_AFTER_FILL',
                                    'net_reward_risk':round(ratio,3),
                                    'minimum':self.min_net_reward_risk,
                                    'timestamp':quote.timestamp.isoformat()})
            self.position={'buy_price':px,'buy_time':quote.timestamp.isoformat(),'quantity':self.quantity,
                           'stop_price':stop,'target_price':target,
                           'planned_net_rr':round(ratio,3),
                           'entry_spread_pct':round(spread_pct,4)}
            return self._event({'event':'PAPER_BUY_FILLED','timestamp':quote.timestamp.isoformat(),
                                'price':px,'quantity':self.quantity,'stop':stop,'target':target,
                                'spread_pct':round(spread_pct,4),'simulated':True})
        if not self.position:raise ValueError('Cannot sell before buy')
        buy=self.position
        fees=option_fees(buy['buy_price'],px,self.quantity,self.exchange,self.fee_profile)
        gross=money((px-buy['buy_price'])*self.quantity)
        net=money(gross-fees['total'])
        event={'event':'PAPER_TRADE_CLOSED','timestamp':quote.timestamp.isoformat(),
               'buy_time':buy['buy_time'],'buy_price':buy['buy_price'],'sell_price':px,
               'quantity':self.quantity,'reason':reason,'gross_pnl':gross,'fees':fees,
               'net_pnl':net,'breakeven_sell_price':breakeven_sell(buy['buy_price'],self.quantity,self.exchange,self.fee_profile),
               'simulated':True,'roundtrip_spread_entry_pct':buy['entry_spread_pct'],
               'spread_exit_pct':round(spread_pct,4)}
        self.position=None
        return self._event(event)

    def summary(self):
        trades=[x for x in self.events if x['event']=='PAPER_TRADE_CLOSED']
        net=sum(x['net_pnl'] for x in trades)
        wins=sum(x['net_pnl']>0 for x in trades)
        unreal=None
        if self.position and self.last_quote:
            hypothetical=realistic_fill(self.last_quote,'SELL',self.quantity,self.slippage_bps)
            if hypothetical:
                gross=(hypothetical-self.position['buy_price'])*self.quantity
                unreal=money(gross-option_fees(self.position['buy_price'],hypothetical,self.quantity,self.exchange,self.fee_profile)['total'])
        return {'mode':'FORWARD_PAPER_NOT_REAL_TRADES','symbol':self.symbol,'fee_profile':self.fee_profile,'closed_trades':len(trades),
                'wins':wins,'win_rate_pct':round(100*wins/len(trades),2) if trades else None,
                'gross_pnl':money(sum(t['gross_pnl'] for t in trades)),
                'total_fees':money(sum(t['fees']['total'] for t in trades)),
                'realized_net_pnl':money(net),'unrealized_net_after_estimated_exit_fees':unreal,
                'open_position':self.position,'roundtrip_trades':trades,
                'warnings':['No actual executions; order book can change between samples',
                            'Includes estimated round-trip exchange charges; does not include data subscriptions, income tax, exchange penalties, exercise/expiry, or auto-squareoff',
                            'Latency and slippage are assumptions, not guaranteed fills']}


def journal_write(file,event):
    p=Path(file);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False,default=str)+'\n')


def replay_csv(path, engine, signal_time=None, journal=None):
    first=True
    with open(path,encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            quote=Quote.from_csv(row)
            signal=not engine.position and first and (signal_time is None or quote.timestamp>=parse_time(signal_time))
            if signal:first=False
            event=engine.process(quote,signal=signal,reason='REPLAY_SIGNAL')
            if event and journal:journal_write(journal,event)
            if event and event['event']=='PAPER_TRADE_CLOSED':break
    return engine.summary()


def export_quote_snapshots(journal,out_csv):
    """Export actually recorded read-only Kite quote snapshots for independent replay."""
    rows=[]
    with Path(journal).open('r',encoding='utf-8') as f:
        for line in f:
            record=json.loads(line)
            if record.get('event')=='QUOTE_SNAPSHOT':
                rows.append({k:record.get(k) for k in ('timestamp','bid','ask','bid_qty','ask_qty','last')})
    if not rows:raise ValueError('Journal contains no recorded quote snapshots')
    path=Path(out_csv);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['timestamp','bid','ask','bid_qty','ask_qty','last'])
        writer.writeheader();writer.writerows(rows)
    return len(rows)
