#!/usr/bin/env python3
"""One-year-at-a-time forex research. Spot proxy, NOT India-executable returns."""
import argparse,csv,datetime as dt,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from forex_backtest import load,bars,simulate,summary

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True);p.add_argument("--pair",required=True);p.add_argument("--year",type=int,required=True)
 p.add_argument("--out",required=True);p.add_argument("--spread-pips",type=float,default=1)
 p.add_argument("--slippage-pips",type=float,default=.2)
 a=p.parse_args()
 data=[x for x in load(a.csv) if x[0].year==a.year]
 if len(data)<10000:raise SystemExit("DATA_UNAVAILABLE: fewer than 10000 valid one-minute bars for selected year")
 if (data[-1][0]-data[0][0]).days<60:raise SystemExit("DATA_UNAVAILABLE: fewer than 60 calendar days covered")
 pip=.01 if a.pair.upper().endswith("JPY") else .0001
 results=[]
 for tf in (5,15,60):
  b=bars(data,tf)
  for kind in ("ema9_15","ema8_21","three_candle","orb","mean_reversion","ema9_pivot"):
   for rr in (1,2,3):
    for stop in ("atr","candle"):
     for session in ("all","00-08","08-16","16-24"):
      trades=simulate(b,kind,rr,stop,session,pip,a.spread_pips,a.slippage_pips)
      results.append({"strategy":kind,"timeframe_minutes":tf,"rr":rr,"stop":stop,"session_utc":session,**summary(trades)})
 ranked=sorted((r for r in results if r["trades"]>=20),key=lambda x:x["net_r"],reverse=True)
 out={"status":"EXPLORATORY_SPOT_PROXY_UNVALIDATED","pair":a.pair,"year":a.year,"partial_year":(data[-1][0].date()<dt.date(a.year,12,20)),"start":data[0][0].isoformat(),"end":data[-1][0].isoformat(),"candles":len(data),"configurations":len(results),"top_in_sample":ranked[:10],"all_results":results,"cost_assumptions":{"spread_pips":a.spread_pips,"slippage_pips_each_side":a.slippage_pips,"commission":"NOT_INCLUDED","NSE_futures_charges":"NOT_INCLUDED"},"warnings":["Single-year in-sample optimization; top rankings are not out-of-sample evidence","No NSE currency futures execution or Indian charges model","No broker orders"]}
 target=pathlib.Path(a.out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,indent=2))
 print(json.dumps({"year":a.year,"pair":a.pair,"candles":len(data),"configurations":len(results),"output":str(target)}))
if __name__=="__main__":main()
