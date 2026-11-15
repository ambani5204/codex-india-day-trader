"""Standalone 365-day NSE equity intraday EMA9 Fibonacci Pivot V2 backtest.

Actual NSE equity 5-minute OHLC, next-bar-open entry, stop-first, same-day
square-off, per-stock cash quantity and indicative intraday equity charges.
Research only. No orders or index/option proxy.
"""
from __future__ import annotations
import argparse,datetime as dt,json,math
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from .core import IST,Bar,parse_time
from .upstox import UpstoxReader,UpstoxError
from .ema9_fib_pivot_research import signals

STOCKS={
"RELIANCE":"INE002A01018","TCS":"INE467B01029","INFY":"INE009A01021",
"HDFCBANK":"INE040A01034","ICICIBANK":"INE090A01021","SBIN":"INE062A01020",
"ITC":"INE154A01025","LT":"INE018A01030","BHARTIARTL":"INE397D01024",
"AXISBANK":"INE238A01034"}
def fetch_stock(reader,symbol,isin,start,end,cache):
    out=[];cursor=start;cache.mkdir(parents=True,exist_ok=True)
    while cursor<=end:
        finish=min(cursor+dt.timedelta(days=26),end)
        path=cache/f"STOCK_{symbol}_{cursor}_{finish}_5m.json"
        if path.exists():
            payload=json.loads(path.read_text())
            if payload.get("instrument_key")!=f"NSE_EQ|{isin}":raise ValueError("Wrong stock cache instrument")
            rows=payload["bars"]
        else:
            key=f"NSE_EQ|{isin}"
            url=f"/v3/historical-candle/{quote(key,safe='')}/minutes/5/{finish}/{cursor}"
            data=reader.get(url)
            if not isinstance(data,dict) or not isinstance(data.get("candles"),list):
                raise UpstoxError("Missing NSE stock historical candles")
            rows=data["candles"]
            path.write_text(json.dumps({"instrument_key":key,"source":"UPSTOX_V3",
                                        "bars":rows}))
        for r in rows:
            t=parse_time(str(r[0]))
            if cursor<=t.date()<=finish:
                out.append(Bar(t,*[float(v) for v in r[1:5]],float(r[5]) if len(r)>5 else 0.))
        cursor=finish+dt.timedelta(days=1)
    if len(set(b.time for b in out))!=len(out):raise ValueError("Duplicate stock bars")
    return sorted(out,key=lambda b:b.time)

def fees(entry,exit_,qty,side,day):
    buy=entry if side==1 else exit_
    sell=exit_ if side==1 else entry
    turnover=(buy+sell)*qty
    brokerage=min(20,buy*qty*.0005)+min(20,sell*qty*.0005)
    stt=sell*qty*.00025
    exchange=turnover*.0000297
    sebi=turnover*.000001
    stamp=buy*qty*.00003
    gst=.18*(brokerage+exchange+sebi)
    return round(brokerage+stt+exchange+sebi+stamp+gst,2)

def run_day(bars,prior,day,rr,capital,slippage_pct):
    clock={b.time:b for b in bars}
    expected=[dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=5*i) for i in range(72)]
    if any(t not in clock for t in expected):return "INCOMPLETE",None
    found=signals(bars,prior,rr=rr)
    if not found:return "OK",None
    s=found[0];side=1 if s["direction"]=="BULL" else -1
    signal_time=dt.datetime.fromisoformat(s["signal_time"])
    if signal_time.time()>=dt.time(15,0):return "OK",None
    entrybar=clock.get(signal_time)
    if not entrybar:return "INCOMPLETE",None
    entry=entrybar.open*(1+side*slippage_pct)
    stop=s["stop"];risk=side*(entry-stop)
    if risk<=0:return "OK",None
    target=entry+side*rr*risk
    qty=math.floor(capital/entry)
    if qty<1:return "OK",None
    future=[b for b in bars if b.time>=entrybar.time and b.time.time()<=dt.time(15,10)]
    if not future or future[-1].time.time()!=dt.time(15,10):return "INCOMPLETE",None
    exit_=None;reason=None
    for b in future:
        if b.time.time()>=dt.time(15,10):
            exit_=b.open*(1-side*slippage_pct);reason="TIME_EXIT";break
        if (side==1 and b.open<=stop) or (side==-1 and b.open>=stop):
            exit_=b.open*(1-side*slippage_pct);reason="GAP_STOP";break
        if (side==1 and b.open>=target) or (side==-1 and b.open<=target):
            exit_=b.open*(1-side*slippage_pct);reason="GAP_TARGET";break
        if (side==1 and b.low<=stop) or (side==-1 and b.high>=stop):
            exit_=stop*(1-side*slippage_pct);reason="STOP_FIRST";break
        if (side==1 and b.high>=target) or (side==-1 and b.low<=target):
            exit_=target*(1-side*slippage_pct);reason="TARGET";break
    if exit_ is None:return "INCOMPLETE",None
    gross=side*(exit_-entry)*qty
    charge=fees(entry,exit_,qty,side,day)
    return "OK",{"day":str(day),"direction":s["direction"],"pivot":s["pivot"],
                 "entry":round(entry,3),"exit":round(exit_,3),"quantity":qty,
                 "gross_inr":round(gross,2),"charges_inr":charge,
                 "net_inr":round(gross-charge,2),"exit_reason":reason}

def summarize(trades):
    gains=sum(max(0,t["net_inr"]) for t in trades)
    losses=-sum(min(0,t["net_inr"]) for t in trades)
    equity=peak=dd=0.
    for t in trades:
        equity+=t["net_inr"];peak=max(peak,equity);dd=min(dd,equity-peak)
    return {"trades":len(trades),"wins":sum(t["net_inr"]>0 for t in trades),
            "win_rate_pct":round(100*sum(t["net_inr"]>0 for t in trades)/len(trades),2) if trades else None,
            "net_inr":round(equity,2),"profit_factor":round(gains/losses,3) if losses else None,
            "max_drawdown_inr":round(dd,2),"winning_trades_at_least_2000":sum(t["net_inr"]>=2000 for t in trades)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True);p.add_argument("--days",type=int,default=365)
    p.add_argument("--capital-per-trade",type=float,default=100000)
    p.add_argument("--slippage-pct",type=float,default=.0005)
    a=p.parse_args()
    if not 30<=a.days<=730 or a.capital_per_trade<=0 or not 0<=a.slippage_pct<=.02:
        p.error("Invalid research parameters")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=a.days-1)
    reader=UpstoxReader();results={};errors={}
    for symbol,isin in STOCKS.items():
        try:
            bars=fetch_stock(reader,symbol,isin,start,end,Path("trader/backtest_cache"))
            days=defaultdict(list)
            for b in bars:days[b.time.date()].append(b)
            ordered=sorted(days);stock={}
            for rr in (2.,3.):
                trades=[];incomplete=0
                for i in range(1,len(ordered)):
                    day=ordered[i];prior=days[ordered[i-1]]
                    if len(prior)<70:incomplete+=1;continue
                    status,trade=run_day(days[day],prior,day,rr,a.capital_per_trade,a.slippage_pct)
                    if status!="OK":incomplete+=1
                    if trade:trades.append(trade)
                stock[f"RR_{int(rr)}"]={**summarize(trades),"incomplete_sessions":incomplete,"trade_details":trades}
            results[symbol]=stock
            print("STOCK",symbol,"2R",stock["RR_2"]["trades"],stock["RR_2"]["net_inr"],flush=True)
        except (UpstoxError,ValueError,OSError) as exc:
            errors[symbol]=str(exc)
            print("STOCK_ERROR",symbol,str(exc),flush=True)
    report={"kind":"EMA9_FIB_V2_NSE_STOCK_INTRADAY_365","start":str(start),"end":str(end),
            "stock_universe":list(STOCKS),"capital_per_trade_inr":a.capital_per_trade,
            "slippage_pct_each_side":a.slippage_pct,"real_orders":False,
            "mode":"HISTORICAL_STOCK_OHLC_SIMULATED_EXECUTION",
            "note":"Ten-stock initial universe, not all NSE equities. Intraday equity fees are estimates; actual broker contract notes may differ.",
            "results":results,"errors":errors}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    if not results:raise RuntimeError("No NSE stock historical datasets succeeded")
    print("STOCK_BACKTEST_COMPLETE",len(results),"ERRORS",len(errors))
if __name__=="__main__":main()
