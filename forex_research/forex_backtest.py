#!/usr/bin/env python3
"""Isolated spot-FX exploratory backtest. NEVER sends orders. CSV timestamps UTC."""
import argparse,csv,datetime as dt,json,math,pathlib,statistics
from collections import defaultdict

def load(path):
    rows=[]
    with open(path,newline="") as f:
        for x in csv.DictReader(f):
            try:
                t=dt.datetime.fromisoformat(x["timestamp"].replace("Z","+00:00"))
                if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
                o,h,l,c=(float(x[k]) for k in ("open","high","low","close"))
                if all(map(math.isfinite,(o,h,l,c))) and l<=min(o,c)<=max(o,c)<=h:rows.append((t,o,h,l,c))
            except (KeyError,ValueError):continue
    rows.sort(key=lambda r:r[0])
    return list({r[0]:r for r in rows}.values())

def bars(rows,n):
    b=defaultdict(list)
    for r in rows:
        t=r[0];minute=(t.hour*60+t.minute)//n*n
        key=t.replace(hour=minute//60,minute=minute%60,second=0,microsecond=0)
        b[key].append(r)
    return [(t,v[0][1],max(x[2] for x in v),min(x[3] for x in v),v[-1][4]) for t,v in sorted(b.items()) if len(v)>=n]

def ema(xs,n):
    out=[];v=None
    for x in xs:
        v=x if v is None else v+2/(n+1)*(x-v);out.append(v)
    return out

def signals(b,kind):
    c=[x[4] for x in b];e9=ema(c,9);e15=ema(c,15);e8=ema(c,8);e21=ema(c,21)
    tr=[x[2]-x[3] if i==0 else max(x[2]-x[3],abs(x[2]-b[i-1][4]),abs(x[3]-b[i-1][4])) for i,x in enumerate(b)]
    atr=ema(tr,14);s=[0]*len(b)
    for i in range(25,len(b)-1):
        if kind in ("ema9_15","ema8_21"):
            a,z=(e9,e15) if kind=="ema9_15" else (e8,e21)
            s[i]=int(a[i]>z[i] and a[i-1]<=z[i-1])-int(a[i]<z[i] and a[i-1]>=z[i-1])
        elif kind=="three_candle":
            s[i]=int(all(b[j][4]>b[j][1] for j in range(i-2,i+1)) and c[i]>max(b[j][2] for j in range(i-3,i)))-int(all(b[j][4]<b[j][1] for j in range(i-2,i+1)) and c[i]<min(b[j][3] for j in range(i-3,i)))
        elif kind=="mean_reversion":
            s[i]=int(c[i]<e21[i]-1.5*atr[i])-int(c[i]>e21[i]+1.5*atr[i])
        elif kind=="orb":
            day=b[i][0].date();today=[x for x in b[:i] if x[0].date()==day]
            if len(today)>=3:
                hi=max(x[2] for x in today[:3]);lo=min(x[3] for x in today[:3])
                s[i]=int(c[i]>hi and c[i-1]<=hi)-int(c[i]<lo and c[i-1]>=lo)
        elif kind=="ema9_pivot":
            previous=[x for x in b[max(0,i-500):i] if x[0].date()<b[i][0].date()]
            if previous:
                y=previous[-1][0].date();previous=[x for x in previous if x[0].date()==y]
                p=(max(x[2] for x in previous)+min(x[3] for x in previous)+previous[-1][4])/3
                s[i]=int(c[i]>p and c[i]>e9[i] and c[i-1]<=e9[i-1])-int(c[i]<p and c[i]<e9[i] and c[i-1]>=e9[i-1])
    return s,atr

def simulate(b,kind,rr,stopmode,session,pip,spread,slip):
    s,atr=signals(b,kind);trades=[];busy=-1
    for i in range(30,len(b)-1):
        if i<=busy or not s[i]:continue
        hour=b[i][0].hour
        if session!="all":
            start,end=map(int,session.split("-"))
            if not start<=hour<end:continue
        side=s[i];entry=b[i+1][1]
        risk=atr[i]*1.5 if stopmode=="atr" else max(abs(entry-(b[i][3] if side==1 else b[i][2])),pip*2)
        if risk<=0:continue
        stop=entry-side*risk;target=entry+side*rr*risk
        exitprice=b[i+1][4];reason="timeout";j=i+1
        for j in range(i+1,min(i+49,len(b))):
            x=b[j]
            if (x[3]<=stop if side==1 else x[2]>=stop):
                exitprice=stop;reason="stop";break
            if (x[2]>=target if side==1 else x[3]<=target):
                exitprice=target;reason="target";break
            exitprice=x[4]
        busy=j
        gross=side*(exitprice-entry)/pip;cost=spread+2*slip
        trades.append({"entry_time":b[i+1][0].isoformat(),"exit_time":b[j][0].isoformat(),"gross_pips":round(gross,5),"cost_pips":cost,"net_pips":round(gross-cost,5),"net_r":round((gross-cost)*pip/risk,5),"exit_reason":reason})
    return trades

def summary(ts):
    p=[t["net_r"] for t in ts];pos=sum(v for v in p if v>0);neg=-sum(v for v in p if v<0)
    e=peak=dd=0
    for v in p:e+=v;peak=max(peak,e);dd=max(dd,peak-e)
    return {"trades":len(p),"win_rate":sum(v>0 for v in p)/len(p) if p else None,"net_r":round(sum(p),3),"net_pips":round(sum(t["net_pips"] for t in ts),3),"profit_factor":round(pos/neg,3) if neg else None,"max_drawdown_r":round(dd,3)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True);p.add_argument("--pair",required=True);p.add_argument("--out",required=True)
    p.add_argument("--spread-pips",type=float,default=1);p.add_argument("--slippage-pips",type=float,default=.2)
    a=p.parse_args();rows=load(a.csv)
    if len(rows)<10000:raise SystemExit("DATA_UNAVAILABLE: fewer than 10000 valid 1-minute bars")
    if (rows[-1][0]-rows[0][0]).days<700:raise SystemExit("DATA_UNAVAILABLE: require at least 700 calendar days of history")
    pip=.01 if a.pair.upper().endswith("JPY") else .0001
    results=[];tradeout=[]
    for timeframe in (1,3,5,10,15,30,60):
        b=bars(rows,timeframe)
        for kind in ("ema9_15","ema8_21","three_candle","orb","mean_reversion","ema9_pivot"):
            for rr in (1,1.5,2,3,4,5):
                for stop in ("atr","candle"):
                    for session in ("all","00-08","08-16","16-24"):
                        ts=simulate(b,kind,rr,stop,session,pip,a.spread_pips,a.slippage_pips)
                        # Chronological partition by entry date; selection only uses training and validation.
                        dates=[t["entry_time"] for t in ts];n=len(ts);train=ts[:int(n*.6)];valid=ts[int(n*.6):int(n*.8)];hold=ts[int(n*.8):]
                        result={"timeframe_minutes":timeframe,"strategy":kind,"rr":rr,"stop":stop,"session_utc":session,"train":summary(train),"validation":summary(valid),"holdout":summary(hold)}
                        result["eligible"]=len(train)>=30 and len(valid)>=10 and all(z["net_r"]>0 and z["profit_factor"] is not None and z["profit_factor"]>=1.1 for z in (result["train"],result["validation"]))
                        results.append(result)
    selected=sorted((x for x in results if x["eligible"]),key=lambda x:(x["validation"]["net_r"],-x["validation"]["max_drawdown_r"]),reverse=True)[:10]
    output={"status":"EXPLORATORY_SPOT_PROXY_NOT_NSE_FUTURES","pair":a.pair,"bars":len(rows),"start":rows[0][0].isoformat(),"end":rows[-1][0].isoformat(),"assumptions":{"spread_pips":a.spread_pips,"slippage_pips_each_side":a.slippage_pips,"commission":"NOT_INCLUDED","swap":"NOT_INCLUDED","NSE_charges":"NOT_INCLUDED"},"configurations":len(results),"top_validation_candidates":selected,"all_results":results,"warning":"Holdout is descriptive only; repeated optimization and missing costs prohibit claims of live profitability."}
    dest=pathlib.Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(output,indent=2))
    print(json.dumps({"status":output["status"],"pair":a.pair,"configurations":len(results),"eligible":len(selected),"output":str(dest)}))
if __name__=="__main__":main()
