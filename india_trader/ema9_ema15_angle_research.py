"""365-day 5m EMA9/EMA15 full-body momentum study; index points, NOT option P&L."""
from __future__ import annotations
import argparse,datetime as dt,json,math
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions,futures_cost_proxy
from .index_intraday_backtest import _LazyHistoricalReader

def evaluate(bars,market,day,angle=30,body_min=.75,stop_mode="after_t1",slippage=1.):
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
        if i<20 or b.time.time()>=dt.time(14,30):continue
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
        entry=b.close+side*slippage;stop=b.low if side==1 else b.high
        risk=side*(entry-stop)
        if risk<=0:continue
        t1=entry+side*2*risk;t2=entry+side*3*risk
        remaining=bars[i+1:]
        if not remaining:continue
        t1_hit=False;exit_=remaining[-1].close-side*slippage;reason="EOD"
        for nxt in remaining:
            # Same-bar ambiguity always resolves adversely (stop before target).
            effective_stop=(entry+side*risk if t1_hit and stop_mode=="after_t1" else stop)
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
               "t1_hit":t1_hit,"trade_management":stop_mode}
        return futures_cost_proxy(trade),"SIGNAL"
    return None,"NO_SIGNAL"

def metrics(trades,statuses):
    n=len(trades);equity=peak=dd=0.;gain=loss=0.
    for t in trades:
        x=t["futures_proxy_net_inr"];equity+=x;peak=max(peak,equity);dd=min(dd,equity-peak)
        gain+=max(0,x);loss+=max(0,-x)
    return {"trades":n,"wins":sum(t["futures_proxy_net_inr"]>0 for t in trades),
            "win_rate_pct":round(100*sum(t["futures_proxy_net_inr"]>0 for t in trades)/n,2) if n else None,
            "net_futures_proxy_inr":round(equity,2),"charges_inr":round(sum(t["futures_proxy_charges_inr"] for t in trades),2),
            "profit_factor":round(gain/loss,3) if loss else None,"max_drawdown_inr":round(dd,2),
            "t1_reached":sum(t["t1_hit"] for t in trades),"statuses":statuses,"trade_details":trades}

def main():
    p=argparse.ArgumentParser();p.add_argument("--days",type=int,default=365);p.add_argument("--out",required=True)
    a=p.parse_args()
    if not 30<=a.days<=730:p.error("days 30..730")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1);start=end-dt.timedelta(days=a.days-1)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    report={"strategy":"EMA9_EMA15_5M_STRONG_CANDLE_V1","start":str(start),"end":str(end),
            "mode":"SPOT_INDEX_FUTURES_COST_PROXY_ONLY","real_orders":False,
            "definition":{"ema_periods":[9,15],"angle_threshold_degrees":30,
                "angle_definition":"atan((EMA9_now-EMA9_previous)/ATR14), degrees, per 5-minute candle",
                "body_min_fraction":.75,"close_near_extreme_fraction":.1,
                "entry":"signal candle close plus 1 index-point adverse slippage",
                "stop":"signal candle low/high","t1":"2R","t2":"3R",
                "trailing_stop":"after T1 bar completes, move stop to +1R for following bars",
                "same_bar_ambiguity":"stop first; T2 cannot fill on T1 bar",
                "one_trade_per_market_per_day":True},
            "warning":"Index-point proxy with estimated futures charges, NOT historical CE/PE premium returns. Close fills idealized. Angle depends on ATR normalization.",
            "markets":{}}
    for market in ("NIFTY","SENSEX"):
        group=[s for s in sessions if s["market"]==market and s["bars"]]
        report["markets"][market]={}
        for mode in ("fixed_t1","after_t1"):
            trades=[];counts={}
            for s in group:
                trade,status=evaluate(s["bars"],market,s["day"],stop_mode=mode)
                counts[status]=counts.get(status,0)+1
                if trade:trades.append(trade)
            report["markets"][market][mode]=metrics(trades,counts)
            print(market,mode,"TRADES",len(trades),"NET",report["markets"][market][mode]["net_futures_proxy_inr"],flush=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__":main()
