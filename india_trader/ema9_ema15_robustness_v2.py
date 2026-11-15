"""Independent EMA9/EMA15 365-day sensitivity, execution, and chronological holdout study.

Research only. Index OHLC futures-cost proxy; NOT actual option premium fills.
"""
from __future__ import annotations
import argparse,datetime as dt,json,math
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions,futures_cost_proxy
from .index_intraday_backtest import _LazyHistoricalReader

def evaluate(bars,market,day,angle=30,body_min=.75,stop_mode="after_t1",slippage=1.,entry_mode="next_open",cutoff=dt.time(14,30),trail_r=1.):
    bars=sorted(bars,key=lambda x:x.time)
    if len(bars)<65:return None,"INCOMPLETE"
    e9=e15=None;prev9=None;atr=None
    # EMA and ATR warm-up on completed same-session candles.
    for i,b in enumerate(bars):
        if i==0:
            e9=e15=b.close;atr=max(.01,b.high-b.low)
        else:
            prev9=e9;e9+=(b.close-e9)*.2;e15+=(b.close-e15)*.125
            tr=max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close))
            atr+=(tr-atr)/14
        if i<20 or b.time.time()>=cutoff:continue
        if prev9 is None or atr<=0:continue
        # angle normalized by prior ATR, not visual chart degrees.
        slope=math.degrees(math.atan((e9-prev9)/atr))
        rng=b.high-b.low
        if rng<=0:continue
        body=abs(b.close-b.open)/rng
        side=1 if e9>e15 and slope>=angle and b.close>b.open and body>=body_min and (b.high-b.close)/rng<=.1 else (
            -1 if e9<e15 and slope<=-angle and b.close<b.open and body>=body_min and (b.close-b.low)/rng<=.1 else 0)
        if not side:continue
        # Close-price entry is an idealized fill. Add adverse 1-point slippage.
        entry=(bars[i+1].open if entry_mode=="next_open" and i+1<len(bars) else b.close)+side*slippage;stop=b.low if side==1 else b.high
        risk=side*(entry-stop)
        if risk<=0:continue
        t1=entry+side*2*risk;t2=entry+side*3*risk
        remaining=bars[i+1:]
        if not remaining:continue
        t1_hit=False;exit_=remaining[-1].close-side*slippage;reason="EOD"
        for nxt in remaining:
            # Same-bar ambiguity always resolves adversely (stop before target).
            effective_stop=(entry+side*trail_r*risk if t1_hit and stop_mode=="after_t1" else stop)
            if (nxt.open-effective_stop)*side<=0:
                exit_=nxt.open-side*slippage;reason="GAP_STOP";break
            if (nxt.low<=effective_stop if side==1 else nxt.high>=effective_stop):
                exit_=effective_stop-side*slippage;reason="TRAIL_STOP" if t1_hit else "STOP";break
            if t1_hit:
                if (nxt.high>=t2 if side==1 else nxt.low<=t2):
                    exit_=t2-side*slippage;reason="T2_3R";break
            elif (nxt.high>=t1 if side==1 else nxt.low<=t1):
                t1_hit=True
                # Stop moves only AFTER bar closes; avoids instantaneous 2R stop-out.
                # T2 is not credited on the T1 candle, even if its range reached T2.
                if stop_mode=="fixed_t1":
                    exit_=t1-side*slippage;reason="T1_2R";break
            if nxt.time.time()>=dt.time(15,10):
                exit_=nxt.close-side*slippage;reason="TIME_EXIT";break
        points=side*(exit_-entry)
        trade={"market":market,"day":str(day),"direction":"BULL" if side==1 else "BEAR",
               "entry":entry,"exit":exit_,"index_points":points,"risk_points":risk,
               "realized_r":round(points/risk,4),"rr":3 if stop_mode=="after_t1" else 2,
               "exit_reason":reason,"entry_time":(b.time+dt.timedelta(minutes=5)).isoformat(),
               "ema_angle_atr_degrees":round(slope,2),"body_fraction":round(body,3),
               "t1_hit":t1_hit,"trade_management":stop_mode,"entry_mode":entry_mode,"trail_r":trail_r}
        return futures_cost_proxy(trade),"SIGNAL"
    return None,"NO_SIGNAL"

def summarize(trades):
    n=len(trades);net=[t["futures_proxy_net_inr"] for t in trades]
    gross_profit=sum(max(0,x) for x in net);gross_loss=-sum(min(0,x) for x in net)
    eq=peak=drawdown=0.
    for x in net:
        eq+=x;peak=max(peak,eq);drawdown=min(drawdown,eq-peak)
    return {"trades":n,"wins":sum(x>0 for x in net),"win_rate_pct":round(100*sum(x>0 for x in net)/n,2) if n else None,
            "net_inr":round(eq,2),"profit_factor":round(gross_profit/gross_loss,3) if gross_loss else None,
            "max_drawdown_inr":round(drawdown,2),"charges_inr":round(sum(t["futures_proxy_charges_inr"] for t in trades),2),
            "t1_hit":sum(bool(t["t1_hit"]) for t in trades),
            "exit_reasons":{k:sum(t["exit_reason"]==k for t in trades) for k in sorted({t["exit_reason"] for t in trades})}}

def main():
    p=argparse.ArgumentParser();p.add_argument("--days",type=int,default=365);p.add_argument("--out",required=True);a=p.parse_args()
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1);start=end-dt.timedelta(days=a.days-1)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    cases=[]
    for angle in (20,30,40):
        for body in (.65,.75,.85):
            for mode in ("fixed_t1","after_t1"):
                cases.append({"angle":angle,"body_min":body,"stop_mode":mode,"entry_mode":"next_open","slippage":1.,"trail_r":1.,"cutoff":dt.time(14,30)})
    for entry_mode in ("signal_close","next_open"):
        for slip in (1.,3.):
            for trail in (0.,1.,2.):
                cases.append({"angle":30,"body_min":.75,"stop_mode":"after_t1","entry_mode":entry_mode,"slippage":slip,"trail_r":trail,"cutoff":dt.time(14,30)})
    for cutoff in (dt.time(11,30),dt.time(13,0),dt.time(14,30)):
        cases.append({"angle":30,"body_min":.75,"stop_mode":"after_t1","entry_mode":"next_open","slippage":1.,"trail_r":1.,"cutoff":cutoff})
    cases=list({json.dumps({k:str(v) for k,v in c.items()},sort_keys=True):c for c in cases}.values())
    split=start+dt.timedelta(days=int(a.days*.7))
    report={"strategy":"EMA9_EMA15_ROBUSTNESS_V2","start":str(start),"end":str(end),
            "split_date":str(split),"training_share":.7,"mode":"INDEX_FUTURES_COST_PROXY_NOT_CE_PE",
            "real_orders":False,"warning":"Parameter sensitivity is exploratory; selected settings must be evaluated on untouched holdout. No historical options premiums. Same-bar stop first.",
            "cases":[]}
    for market in ("NIFTY","SENSEX"):
        group=[s for s in sessions if s["market"]==market and s["bars"]]
        for case in cases:
            trades=[];statuses={}
            for s in group:
                t,status=evaluate(s["bars"],market,s["day"],**case)
                statuses[status]=statuses.get(status,0)+1
                if t:trades.append(t)
            training=[t for t in trades if t["day"]<str(split)]
            holdout=[t for t in trades if t["day"]>=str(split)]
            report["cases"].append({"market":market,"parameters":{k:str(v) for k,v in case.items()},
                "training":summarize(training),"holdout":summarize(holdout),
                "all":summarize(trades),"statuses":statuses})
        print("COMPLETED",market,len(cases),"configurations",flush=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__":main()
