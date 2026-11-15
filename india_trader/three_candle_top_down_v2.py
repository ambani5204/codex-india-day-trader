"""V2 independently specified 365-day top-down sweep / hourly rejection / OB retest.

No live orders. This is a different, more faithful, non-optimized hypothesis
than V1; do not interpret an improved result as evidence of robustness.
"""
from __future__ import annotations
import argparse,datetime as dt,json
from collections import Counter
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions,futures_cost_proxy
from .index_intraday_backtest import _LazyHistoricalReader

def test_day(bars,prior,market,day,rr):
    clock={b.time:b for b in bars}
    expected=[dt.datetime.combine(day,dt.time(9,15),IST)+dt.timedelta(minutes=5*i) for i in range(75)]
    if any(t not in clock for t in expected):return "INCOMPLETE",None,Counter()
    seq=[clock[t] for t in expected]
    pdh=max(b.high for b in prior);pdl=min(b.low for b in prior)
    stages=Counter();bias=None;sweep_idx=None;hour_idx=None;zone=None;position=None
    for i,b in enumerate(seq):
        if position and i>=position["entry_i"]:
            side=position["side"];stop=position["stop"];target=position["target"]
            if (side==1 and b.open<=stop) or (side==-1 and b.open>=stop):
                exit_=b.open-side;reason="GAP_STOP"
            elif (side==1 and b.open>=target) or (side==-1 and b.open<=target):
                exit_=b.open-side;reason="GAP_TARGET"
            elif (side==1 and b.low<=stop) or (side==-1 and b.high>=stop):
                exit_=stop-side;reason="STOP_FIRST"
            elif (side==1 and b.high>=target) or (side==-1 and b.low<=target):
                exit_=target-side;reason="TARGET"
            elif b.time.time()>=dt.time(15,10):
                exit_=b.open-side;reason="TIME_EXIT"
            else:continue
            entry=position["entry"];points=side*(exit_-entry)
            t={"market":market,"day":str(day),"direction":"BULL" if side==1 else "BEAR",
               "entry":entry,"exit":exit_,"index_points":points,"risk_points":position["risk"],
               "realized_r":points/position["risk"],"rr":rr,"exit_reason":reason,
               "entry_time":position["entry_time"],"sweep_time":position["sweep_time"],
               "order_block":position["order_block"]}
            return "OK",futures_cost_proxy(t),stages
        if b.time.time()>=dt.time(14,45):continue
        # State 1: completed 5m candle must sweep and reclaim previous day's extreme.
        if bias is None:
            if b.low<pdl and b.close>pdl:
                bias=1;sweep_idx=i;stages["daily_sweep_reclaim"]+=1
            elif b.high>pdh and b.close<pdh:
                bias=-1;sweep_idx=i;stages["daily_sweep_reclaim"]+=1
            continue
        # State 2: subsequent completed 5m candle rejects preceding completed
        # 60m rolling range in direction of the sweep (hourly proxy).
        if hour_idx is None and i>=12 and i>sweep_idx:
            prior_hour=seq[i-12:i]
            h=max(x.high for x in prior_hour);l=min(x.low for x in prior_hour)
            if (bias==1 and b.low<l and b.close>l) or (bias==-1 and b.high>h and b.close<h):
                hour_idx=i;stages["hourly_rejection"]+=1
            if i-sweep_idx>30:return "OK",None,stages
            continue
        # State 3: subsequent bullish/bearish displacement breaking last 3
        # completed 5m bars. OB is last opposite candle before displacement.
        if zone is None and hour_idx is not None and i>hour_idx:
            prior3=seq[i-3:i]
            body=abs(b.close-b.open);rng=b.high-b.low
            impulse=(rng>0 and body>=.55*rng and
                     ((bias==1 and b.close>max(x.high for x in prior3)) or
                      (bias==-1 and b.close<min(x.low for x in prior3))))
            if impulse:
                opposing=[x for x in seq[max(sweep_idx,i-6):i]
                          if (x.close<x.open if bias==1 else x.close>x.open)]
                if opposing:
                    ob=opposing[-1]
                    zone=(ob.low,ob.high,i)
                    stages["displacement_order_block"]+=1
            if i-hour_idx>18:return "OK",None,stages
            continue
        # State 4: later OB touch, enter at following candle open. No lookahead.
        if zone is not None and i>zone[2]:
            low,high,formed=zone
            if b.low<=high and b.high>=low and i+1<len(seq):
                nxt=seq[i+1];entry=nxt.open+bias
                stop=low-1 if bias==1 else high+1
                risk=bias*(entry-stop)
                if 0<risk<=entry*.012:
                    stages["valid_retest_entry"]+=1
                    position={"side":bias,"entry":entry,"stop":stop,"risk":risk,
                              "target":entry+bias*rr*risk,"entry_i":i+1,
                              "entry_time":nxt.time.isoformat(),
                              "sweep_time":seq[sweep_idx].time.isoformat(),
                              "order_block":[low,high]}
                else:stages["invalid_risk"]+=1
                if position is None:return "OK",None,stages
            if i-formed>18:return "OK",None,stages
    return "OK",None,stages

def summary(trades,stages,incomplete):
    n=len(trades);gain=sum(max(0,t["futures_proxy_net_inr"]) for t in trades)
    loss=-sum(min(0,t["futures_proxy_net_inr"]) for t in trades)
    equity=peak=drawdown=0.
    for t in trades:
        equity+=t["futures_proxy_net_inr"];peak=max(peak,equity)
        drawdown=min(drawdown,equity-peak)
    return {"trades":n,"wins":sum(t["futures_proxy_net_inr"]>0 for t in trades),
            "win_rate_pct":round(100*sum(t["futures_proxy_net_inr"]>0 for t in trades)/n,2) if n else None,
            "net_futures_proxy_inr":round(equity,2),"charges_inr":round(sum(t["futures_proxy_charges_inr"] for t in trades),2),
            "profit_factor":round(gain/loss,3) if loss else None,
            "max_drawdown_inr":round(drawdown,2),"incomplete_sessions":incomplete,
            "filter_counts":dict(stages),"trade_details":trades}

def main():
    p=argparse.ArgumentParser();p.add_argument("--days",type=int,default=365)
    p.add_argument("--out",required=True);a=p.parse_args()
    if not 30<=a.days<=730:p.error("days must be 30..730")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=a.days-1)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    report={"strategy":"3_CANDLE_TOP_DOWN_MECHANICAL_V2","start":str(start),"end":str(end),
            "mode":"SPOT_INDEX_FUTURES_COST_PROXY_ONLY","real_orders":False,
            "warning":"V2 relaxes V1's simultaneous rejection+displacement condition; not optimized or proof of profitable edge. 60m rolling range is a proxy, not native hourly candles. No option premium or 2m data.",
            "markets":{}}
    for market in ("NIFTY","SENSEX"):
        group=sorted((s for s in sessions if s["market"]==market and s["bars"]),key=lambda s:s["day"])
        result={}
        for rr in (2.,3.):
            trades=[];counts=Counter();incomplete=0
            for prev,cur in zip(group,group[1:]):
                if len(prev["bars"])<70:incomplete+=1;continue
                status,trade,stages=test_day(cur["bars"],prev["bars"],market,cur["day"],rr)
                counts.update(stages)
                if status=="INCOMPLETE":incomplete+=1
                if trade:trades.append(trade)
            result[f"RR_{int(rr)}"]=summary(trades,counts,incomplete)
            print(market,rr,"TRADES",len(trades),"NET",result[f"RR_{int(rr)}"]["net_futures_proxy_inr"],"FILTERS",dict(counts),flush=True)
        report["markets"][market]=result
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__":main()
