"""V4 research-only competing reversal models, rolling out-of-sample validation."""
import argparse
import datetime as dt
import itertools
import json
from collections import defaultdict
from statistics import mean,pstdev
from india_trader.core import read_bars
from deploy.mean_reversion_365d import resample,summarize

def candidate(bars,i,model,threshold):
    bar,prev=bars[i],bars[i-1]
    lookback=min(20,max(8,int(60 / max(1,(bars[1].time-bars[0].time).total_seconds()/60))))
    hist=bars[i-lookback:i]
    closes=[x.close for x in hist]
    avg=mean(closes)
    sd=pstdev(closes)
    if sd<=0: return None
    # VWAP is valid only with positive actual volumes; no synthetic volume.
    volume=sum(x.volume for x in bars[:i+1])
    vwap=sum(x.close*x.volume for x in bars[:i+1])/volume if volume>0 else None
    if model=="z_reversal":
        direction=1 if prev.close<avg-threshold*sd and bar.close>prev.close else (-1 if prev.close>avg+threshold*sd and bar.close<prev.close else 0)
        anchor=avg
    elif model=="failed_breakout":
        low=min(x.low for x in hist)
        high=max(x.high for x in hist)
        direction=1 if bar.low<low and bar.close>low else (-1 if bar.high>high and bar.close<high else 0)
        anchor=avg
    elif model=="vwap_reclaim":
        if vwap is None: return None
        direction=1 if prev.close<vwap-threshold*sd and bar.close>prev.close else (-1 if prev.close>vwap+threshold*sd and bar.close<prev.close else 0)
        anchor=vwap
    else: raise ValueError(model)
    if not direction or direction*(bar.close-bar.open)<=0: return None
    if direction*(anchor-bar.close)<=0: return None
    return direction,anchor

def evaluate(bars,model,threshold,rr,cost_bps,diagnostics=None):
    def count(key):
        if diagnostics is not None: diagnostics[key]=diagnostics.get(key,0)+1
    if len(bars)<12: return None
    lookback=min(20,max(8,int(60 / max(1,(bars[1].time-bars[0].time).total_seconds()/60))))
    for i in range(lookback,len(bars)-1):
        b=bars[i]
        if not dt.time(10,0)<=b.time.time()<dt.time(14,0): continue
        found=candidate(bars,i,model,threshold)
        if not found:
            count('no_reversal_setup')
            continue
        count('reversal_setup')
        direction,anchor=found
        entry=bars[i+1].open
        stop=b.low if direction==1 else b.high
        risk=direction*(entry-stop)
        if risk<=0 or risk/entry>.01 or risk/entry<.0001:
            count('invalid_candle_stop')
            continue
        # Conservative round-trip index proxy cost, expressed in risk units.
        if entry*cost_bps/10000>.5*risk:
            count('cost_too_large_for_stop')
            continue
        if direction*(anchor-entry)<rr*risk:
            count('insufficient_room_to_mean')
            continue
        count('tradable_signal')
        target=entry+direction*rr*risk
        exit_price=bars[-1].close
        reason="SESSION_CLOSE"
        for future in bars[i+1:]:
            stop_hit=future.low<=stop if direction==1 else future.high>=stop
            target_hit=future.high>=target if direction==1 else future.low<=target
            if stop_hit:
                exit_price=min(future.open,stop) if direction==1 else max(future.open,stop)
                reason="STOP"
                break
            if target_hit:
                exit_price=max(future.open,target) if direction==1 else min(future.open,target)
                reason="TARGET"
                break
        net_r=(direction*(exit_price-entry)-entry*cost_bps/10000)/risk
        return {"date":str(b.time.date()),"net_r":round(net_r,6),"reason":reason}
    return None

def research(path,cost_bps):
    raw=read_bars(path)
    dates=sorted({x.time.date() for x in raw})
    if not dates or (dates[-1]-dates[0]).days<1094:
        raise ValueError("V4 requires >=1095 calendar days genuine data")
    outcomes={}
    # 5m and 15m first: six models/thresholds x two RRs; fewer degrees of freedom.
    for minutes in (5,15):
        byday=defaultdict(list)
        for b in resample(raw,minutes): byday[b.time.date()].append(b)
        configurations=list(itertools.product(("z_reversal","failed_breakout","vwap_reclaim"),(1.5,2.0),(1.,2.)))
        cache={}
        rejection_diagnostics={}
        for model,threshold,rr in configurations:
            diagnostic={}
            cache[(model,threshold,rr)]={
                d:trade for d in dates
                if (trade:=evaluate(byday[d],model,threshold,rr,cost_bps,diagnostic)) is not None
            }
            rejection_diagnostics[f'{model}_z{threshold}_rr{rr}']=diagnostic
        # Expanding train / forward-only test, three separate out-of-sample blocks.
        windows=[(.4,.6),(.6,.8),(.8,1.)]
        folds=[]
        training_diagnostics=[]
        for train_frac,end_frac in windows:
            cut=int(len(dates)*train_frac)
            end=min(len(dates),int(len(dates)*end_frac))
            ranked=[]
            training_rank=[]
            for cfg,trades in cache.items():
                s=summarize([trades[d] for d in dates[:cut] if d in trades])
                training_rank.append({"model":cfg[0],"threshold":cfg[1],"reward_risk":cfg[2],**s})
                if s["trades"]>=30 and s["net_r"]>0 and (s["profit_factor"] or 0)>1:
                    ranked.append((s["net_r"],cfg))
            training_diagnostics.append({"train_sessions":cut,"top_by_net_r":sorted(training_rank,key=lambda x:x["net_r"],reverse=True)[:5],"models_with_30_trades":sum(x["trades"]>=30 for x in training_rank)})
            if not ranked:
                folds.append({"status":"NO_POSITIVE_TRAINING_MODEL","test_sessions":end-cut})
                continue
            _,cfg=max(ranked)
            trades=cache[cfg]
            holdout=summarize([trades[d] for d in dates[cut:end] if d in trades])
            folds.append({"status":"TESTED","model":cfg[0],"threshold":cfg[1],
                          "reward_risk":cfg[2],"test_sessions":end-cut,"holdout":holdout})
        tested=[x for x in folds if x["status"]=="TESTED"]
        net=sum(x["holdout"]["net_r"] for x in tested)
        count=sum(x["holdout"]["trades"] for x in tested)
        profitable=sum(x["holdout"]["net_r"]>0 for x in tested)
        outcomes[f"{minutes}m"]={"folds":folds,"training_diagnostics":training_diagnostics,"rejection_diagnostics":rejection_diagnostics,"total_holdout_trades":count,
           "total_holdout_net_r":round(net,3),
           "positive_folds":profitable,
           "qualified":len(tested)==3 and count>=100 and profitable>=2 and net>0}
    return {"sessions":len(dates),"calendar_days":(dates[-1]-dates[0]).days+1,
            "timeframes":outcomes}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--nifty",required=True)
    p.add_argument("--sensex",required=True)
    p.add_argument("--cost-bps",type=float,default=10)
    p.add_argument("--output",default="mean_reversion_v4_results.json")
    args=p.parse_args()
    if args.cost_bps<0: p.error("negative costs")
    result={"kind":"MEAN_REVERSION_V4_RESEARCH_INDEX_PROXY","trade_instrument":"NONE_INDEX_SIGNAL_RESEARCH_ONLY","option_pnl_verified":False,"deployable":False,"cost_bps":args.cost_bps,
      "NIFTY":research(args.nifty,args.cost_bps),
      "SENSEX":research(args.sensex,args.cost_bps),
      "warning":"NOT AN OPTIONS BACKTEST: index candles cannot establish CE/PE premium P&L, strike, expiry, lot size, bid/ask, STT, fees or fills. Do not deploy. No broker orders."}
    with open(args.output,"w") as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
