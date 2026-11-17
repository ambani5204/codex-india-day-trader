#!/usr/bin/env python3
"""Fixed-parameter, yearly EURUSD 2024-selected strategy trade ledger; paper-only."""
import argparse,csv,datetime as dt,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from forex_backtest import load,bars,simulate,summary

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True);p.add_argument("--pair",default="EURUSD")
 p.add_argument("--year",type=int,required=True);p.add_argument("--out-dir",required=True)
 p.add_argument("--risk-inr",type=float,default=500)
 a=p.parse_args()
 rows=[r for r in load(a.csv) if r[0].year==a.year]
 if len(rows)<10000:raise SystemExit("DATA_UNAVAILABLE: fewer than 10000 valid bars")
 pip=.01 if a.pair.upper().endswith("JPY") else .0001
 trades=simulate(bars(rows,60),"ema9_pivot",3,"atr","00-08",pip,1,.2)
 out=pathlib.Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 for t in trades:
  t["hypothetical_pnl_inr"]=round(t["net_r"]*a.risk_inr,2)
  t["risk_inr"]=a.risk_inr
 with (out/(a.pair.lower()+"-"+str(a.year)+"-trades.csv")).open("w",newline="") as f:
  if trades:
   w=csv.DictWriter(f,fieldnames=list(trades[0]));w.writeheader();w.writerows(trades)
 report={"pair":a.pair,"year":a.year,"strategy":"ema9_pivot","timeframe_minutes":60,"rr":3,"stop":"atr","session_utc":"00-08","selection":"2024 in-sample winner; fixed unchanged for other years","candles":len(rows),"summary":summary(trades),"hypothetical_risk_per_trade_inr":a.risk_inr,"hypothetical_total_pnl_inr":round(sum(t["hypothetical_pnl_inr"] for t in trades),2),"trades":trades,"limitations":["This is an in-sample selection for 2024; 2023 is backward validation, 2025 forward validation","Hypothetical INR values use fixed cash risk, not a broker/contract lot size","Missing commission, swaps, Indian futures fees, contract rollover, actual executable spread","Trade ledger contains entry/exit timestamps and pips/R, not entry/exit quote prices; requires engine change for full fill ledger"]}
 (out/(a.pair.lower()+"-"+str(a.year)+"-detail.json")).write_text(json.dumps(report,indent=2))
 print(json.dumps({"year":a.year,"trades":len(trades),"net_r":report["summary"]["net_r"],"hypothetical_pnl_inr":report["hypothetical_total_pnl_inr"]}))
if __name__=="__main__":main()
