"""Research-only mechanical interpretation of reel '3 Candle Top Down'.

Uses 5-minute spot index bars for PDH/PDL sweep, last completed rolling
60-minute range, displacement, order block and retest. No future knowledge.
NOT an exact reproduction of discretionary chart annotations, not option P&L.
"""
from __future__ import annotations
import argparse,datetime as dt,json
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions,futures_cost_proxy
from .index_intraday_backtest import _LazyHistoricalReader

def simulate(daybars,previous,market,day,rr):
    bars=sorted(daybars,key=lambda b:b.time)
    times=[dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=5*i) for i in range(75)]
    clock={b.time:b for b in bars}
    if any(t not in clock for t in times):return "INCOMPLETE",None
    bars=[clock[t] for t in times]
    pdh=max(b.high for b in previous);pdl=min(b.low for b in previous)
    # First 5m completed sweep and reclaim during the session; no daily close lookahead.
    bias=0;sweep_at=None;setup=None;position=None
    for i,b in enumerate(bars):
        if b.time.time()>=dt.time(15,15):break
        if position:
            side=position["side"];stop=position["stop"];target=position["target"]
            if (side==1 and b.open<=stop) or (side==-1 and b.open>=stop):
                price=b.open-side;reason="GAP_STOP"
            elif (side==1 and b.open>=target) or (side==-1 and b.open<=target):
                price=b.open-side;reason="GAP_TARGET"
            elif (side==1 and b.low<=stop) or (side==-1 and b.high>=stop):
                price=stop-side;reason="STOP_FIRST"
            elif (side==1 and b.high>=target) or (side==-1 and b.low<=target):
                price=target-side;reason="TARGET"
            elif b.time.time()>=dt.time(15,10):
                price=b.open-side;reason="TIME_EXIT"
            else:continue
            entry=position["entry"];points=side*(price-entry)
            trade={"market":market,"day":str(day),"direction":"BULL" if side==1 else "BEAR",
                   "entry":entry,"exit":price,"index_points":points,
                   "risk_points":position["risk"],"realized_r":points/position["risk"],
                   "rr":rr,"exit_reason":reason,"entry_time":position["entry_time"],
                   "sweep_time":position["sweep_time"],"order_block":position["order_block"]}
            return "OK",futures_cost_proxy(trade)
        if i>=12 and setup and b.time.time()<=dt.time(14,30):
            # First retest after displacement: enter next bar open only if OB touched.
            side=setup["side"]
            touched=b.low<=setup["zone_high"] and b.high>=setup["zone_low"]
            if i>setup["formed_at"] and touched and i+1<len(bars):
                nxt=bars[i+1]
                if nxt.time.time()>dt.time(14,45):return "OK",None
                entry=nxt.open+side
                stop=(setup["zone_low"]-1 if side==1 else setup["zone_high"]+1)
                risk=side*(entry-stop)
                if risk>0 and risk<=max(20,entry*.012):
                    position={"side":side,"entry":entry,"stop":stop,
                              "target":entry+side*rr*risk,"risk":risk,
                              "entry_time":nxt.time.isoformat(),
                              "sweep_time":setup["sweep_time"],
                              "order_block":[setup["zone_low"],setup["zone_high"]]}
                    # Position becomes active on next bar, not the retest candle.
                else:return "OK",None
                setup=None
                continue
        if not bias and i>=1:
            if b.low<pdl and b.close>pdl:
                bias=1;sweep_at=i
            elif b.high>pdh and b.close<pdh:
                bias=-1;sweep_at=i
        if bias and not setup and sweep_at is not None and i>=max(12,sweep_at+1):
            if i>min(sweep_at+24,len(bars)-1):return "OK",None
            # Completed prior 60 minutes only (not the active hourly candle).
            hour=bars[i-12:i]
            hi=max(x.high for x in hour);lo=min(x.low for x in hour)
            # Reversal must reject previous hourly low/high then reclaim it.
            if bias==1 and not (b.low<lo and b.close>lo):continue
            if bias==-1 and not (b.high>hi and b.close<hi):continue
            # Displacement closes beyond last 3 completed 5m highs/lows.
            recent=bars[i-3:i]
            if bias==1 and b.close<=max(x.high for x in recent):continue
            if bias==-1 and b.close>=min(x.low for x in recent):continue
            # Body >= 60% candle range.
            if b.high<=b.low or abs(b.close-b.open)<.6*(b.high-b.low):continue
            opposing=[x for x in bars[max(sweep_at,i-5):i] if (x.close<x.open if bias==1 else x.close>x.open)]
            if not opposing:continue
            ob=opposing[-1]
            setup={"side":bias,"zone_low":ob.low,"zone_high":ob.high,
                   "formed_at":i,"sweep_time":bars[sweep_at].time.isoformat()}
    return "OK",None

def metrics(trades):
    n=len(trades);wins=sum(t["futures_proxy_net_inr"]>0 for t in trades)
    gain=sum(max(0,t["futures_proxy_net_inr"]) for t in trades)
    loss=-sum(min(0,t["futures_proxy_net_inr"]) for t in trades)
    equity=peak=dd=0
    for t in trades:
        equity+=t["futures_proxy_net_inr"];peak=max(peak,equity);dd=min(dd,equity-peak)
    return {"trades":n,"wins":wins,"win_rate_pct":round(100*wins/n,2) if n else None,
            "net_futures_proxy_inr":round(equity,2),"charges_inr":round(sum(t["futures_proxy_charges_inr"] for t in trades),2),
            "profit_factor":round(gain/loss,3) if loss else None,
            "max_drawdown_inr":round(dd,2),"avg_net_r":round(sum(t["net_proxy_r"] for t in trades)/n,3) if n else None}

def main():
    p=argparse.ArgumentParser();p.add_argument("--days",type=int,default=365)
    p.add_argument("--out",required=True);a=p.parse_args()
    if not 30<=a.days<=730:p.error("days must be 30..730")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=a.days-1)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    report={"strategy":"3_CANDLE_TOP_DOWN_MECHANICAL_V1","start":str(start),"end":str(end),
            "mode":"SPOT_INDEX_FUTURES_COST_PROXY_ONLY","real_orders":False,
            "limitations":["Daily bias implemented as same-session 5m sweep/reclaim of prior day high/low, not completed daily candle",
                           "1h setup approximated with preceding 12 completed 5m candles, not exchange-aligned 1h bars",
                           "Order block last opposing 5m candle before strong swing-break displacement; first retest",
                           "One point adverse slippage per side; stop first on ambiguous candles",
                           "No historical CE/PE premiums or actual futures margin modeled"],
            "markets":{}}
    for market in ("NIFTY","SENSEX"):
        group=sorted((s for s in sessions if s["market"]==market and s["bars"]),key=lambda s:s["day"])
        results={}
        for rr in (2.,3.):
            trades=[];incomplete=0
            for prev,current in zip(group,group[1:]):
                if len(prev["bars"])<70:incomplete+=1;continue
                status,trade=simulate(current["bars"],prev["bars"],market,current["day"],rr)
                if status=="INCOMPLETE":incomplete+=1
                if trade:trades.append(trade)
            results[f"RR_{int(rr)}"]={**metrics(trades),"incomplete_sessions":incomplete,"trade_details":trades}
            print(market,rr,"TRADES",len(trades),"NET",results[f"RR_{int(rr)}"]["net_futures_proxy_inr"],flush=True)
        report["markets"][market]=results
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n")
    print("COMPLETE",str(path))
if __name__=="__main__":main()
