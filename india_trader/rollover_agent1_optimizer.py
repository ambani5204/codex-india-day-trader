"""Agent 1: bounded train/validation/holdout rollover research, never deployment."""
import argparse,datetime as dt,itertools,json
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions
from .index_intraday_backtest import _LazyHistoricalReader
from .nifty_expiry_rollover_research import replay

def score(rows):
    trades=[t for r in rows if r["status"]=="OK" for t in r["trades"]]
    gains=[t["index_points"] for t in trades if t["index_points"]>0]
    losses=[-t["index_points"] for t in trades if t["index_points"]<0]
    equity=peak=dd=0.
    for t in trades:
        equity+=t["index_points"];peak=max(peak,equity);dd=min(dd,equity-peak)
    return {"trades":len(trades),"wins":len(gains),
            "win_rate_pct":round(100*len(gains)/len(trades),2) if trades else None,
            "net_index_points":round(sum(t["index_points"] for t in trades),3),
            "profit_factor":round(sum(gains)/sum(losses),3) if losses else None,
            "max_drawdown_points":round(dd,3),
            "total_r":round(sum(t["realized_r"] for t in trades),3),
            "min_win_points":round(min(gains),3) if gains else None,
            "max_loss_points":round(max(losses),3) if losses else None,
            "option_pnl_inr":None,
            "target_rupees_2000_verified":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=364)
    sessions=[x for x in _load_sessions(start,end,"NIFTY",_LazyHistoricalReader(),"trader/backtest_cache") if x["bars"]]
    sessions.sort(key=lambda x:x["day"])
    n=len(sessions)
    if n<150:raise RuntimeError("Insufficient historical sessions")
    train=sessions[:int(.6*n)];valid=sessions[int(.6*n):int(.8*n)];hold=sessions[int(.8*n):]
    configs=[dict(preceding=pre,min_body_ratio=body,min_range_multiple=mult,rr=rr)
             for pre,body,mult,rr in itertools.product((2,3,4),(.5,.65), (1.,1.3), (1.5,2.,3.))]
    ranked=[]
    for c in configs:
        tr=score([replay(x["bars"],x["day"],**c) for x in train])
        va=score([replay(x["bars"],x["day"],**c) for x in valid])
        # No selection on final holdout. Require enough trades and positive validation.
        eligible=tr["trades"]>=8 and va["trades"]>=3 and va["net_index_points"]>0
        ranked.append((eligible,va["net_index_points"],tr["net_index_points"],c,tr,va))
    ranked.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    best=next((x for x in ranked if x[0]),None)
    result={"kind":"NIFTY_LATE_ROLLOVER_AGENT1","period":[str(start),str(end)],
            "split_sessions":{"train":len(train),"validation":len(valid),"holdout":len(hold)},
            "configs_tested":len(configs),"target":"At least INR 2000 per winning trade with minimal loss",
            "warning":"Only spot index OHLC is available. INR 2000 profit/trade cannot be verified without executable instrument and quantity.",
            "selected_params":best[3] if best else None,
            "train":best[4] if best else None,"validation":best[5] if best else None,
            "holdout":score([replay(x["bars"],x["day"],**best[3]) for x in hold]) if best else None,
            "status":"RESEARCH_CANDIDATE_NOT_APPROVED" if best else "NO_VALIDATED_EDGE"}
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
