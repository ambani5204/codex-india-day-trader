"""Shared research-only intraday execution accounting.

INTRADAY: cash-equity trades, charges approximated for Zerodha.
OPTIONS: actual timestamped CE/PE bid/ask quotes, complete contract identity.
Never derive historical option premiums from index candles. No broker orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from india_trader.paper_sim import option_fees, realistic_fill, Quote, money

@dataclass(frozen=True)
class OptionContract:
    symbol: str
    exchange: str
    expiry: str
    strike: float
    option_type: str
    lot_size: int
    def __post_init__(self):
        if self.exchange not in ("NFO","BFO") or self.option_type not in ("CE","PE"):
            raise ValueError("Only NFO/BFO CE/PE contracts supported")
        if self.lot_size<=0 or self.strike<=0 or not self.symbol or not self.expiry:
            raise ValueError("Missing historical contract metadata")

def option_roundtrip(contract, entry:Quote, exit:Quote, lots=1, broker="ZERODHA", slippage_bps=5):
    """Real historical quote replay; refuse missing or stale option depth."""
    if lots<=0 or int(lots)!=lots or entry.timestamp>=exit.timestamp:
        raise ValueError("Invalid quantity or timestamps")
    if entry.timestamp.date()!=exit.timestamp.date():
        raise ValueError("Intraday options must exit the same session")
    quantity=contract.lot_size*lots
    buy=realistic_fill(entry,"BUY",quantity,slippage_bps)
    sell=realistic_fill(exit,"SELL",quantity,slippage_bps)
    if buy is None or sell is None:
        raise ValueError("Insufficient actual option order-book depth")
    fees=option_fees(buy,sell,quantity,contract.exchange,broker)
    return {"mode":"OPTIONS","symbol":contract.symbol,"contract":contract.__dict__,
            "entry":buy,"exit":sell,"quantity":quantity,"gross_inr":money((sell-buy)*quantity),
            "charges":fees,"net_inr":money((sell-buy)*quantity-fees["total"]),
            "execution":"HISTORICAL_BID_ASK_DEPTH","verified_option_quotes":True}

def equity_intraday_roundtrip(buy,sell,quantity,slippage_bps=5,brokerage_per_order=20):
    """Cash-equity intraday BUY then SELL, not futures or options.

    Approximate NSE equity intraday charges (Zerodha published schedule).
    No historical execution proof without actual equity bid/ask data.
    """
    if min(buy,sell,quantity)<=0 or int(quantity)!=quantity:
        raise ValueError("Invalid prices/quantity")
    entry=buy*(1+slippage_bps/10000)
    exit=sell*(1-slippage_bps/10000)
    bt,st=entry*quantity,exit*quantity
    turnover=bt+st
    brokerage=min(bt*.0003,brokerage_per_order)+min(st*.0003,brokerage_per_order)
    exchange=turnover*.0000307
    sebi=turnover*.000001
    gst=.18*(brokerage+exchange+sebi)
    stamp=bt*.00003
    stt=st*.00025
    charges=money(brokerage+exchange+sebi+gst+stamp+stt)
    return {"mode":"INTRADAY_EQUITY","gross_inr":money((exit-entry)*quantity),
            "charges_inr":charges,"net_inr":money((exit-entry)*quantity-charges),
            "execution":"EQUITY_PRICE_PROXY","verified_option_quotes":False}

def require_option_validation(result):
    if result.get("mode")!="OPTIONS" or not result.get("verified_option_quotes"):
        raise ValueError("Cannot promote index/equity proxy results as option trading results")
    return result
