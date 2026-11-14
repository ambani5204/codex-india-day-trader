"""Weekly EMA9 V2 paper summary from Firestore, separated by market and track."""
import datetime as dt
import json
import os
from pathlib import Path
from india_trader.core import IST
from deploy.nightly_strategy_evaluation import unpack, firestore_field

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session=AuthorizedSession(creds)
    base=("https://firestore.googleapis.com/v1/projects/"+os.environ["FIREBASE_PROJECT_ID"]+
          "/databases/(default)/documents/")
    today=dt.datetime.now(IST).date()
    monday=today-dt.timedelta(days=today.weekday())
    start=monday-dt.timedelta(days=7)
    end=monday-dt.timedelta(days=1)
    rows=[];token=""
    while True:
        response=session.get(base+"ema9_v2_paper",
            params={"pageSize":100,**({"pageToken":token} if token else {})},timeout=30)
        if response.status_code==404:break
        response.raise_for_status()
        payload=response.json()
        rows.extend({k:unpack(v) for k,v in d.get("fields",{}).items()}
                    for d in payload.get("documents",[]))
        token=payload.get("nextPageToken","")
        if not token:break
    report={"kind":"EMA9_V2_WEEKLY_PAPER_RESEARCH","week_start":start.isoformat(),
            "week_end":end.isoformat(),"source":"FIRESTORE_EMA9_V2_PAPER",
            "markets":{},"real_order_execution":False}
    for market in ("NIFTY","SENSEX"):
        report["markets"][market]={}
        for track in ("OPTION_BUY","INTRADAY"):
            subset=[r for r in rows if r.get("market")==market and r.get("track")==track
                    and start.isoformat()<=str(r.get("date_ist",""))<=end.isoformat()]
            closed=sum(int(r.get("closed_trades") or 0) for r in subset)
            verified=sum(int(r.get("verified_pnl_trades") or 0) for r in subset)
            pnl=[r["net_pnl_inr"] for r in subset if isinstance(r.get("net_pnl_inr"),(int,float))]
            report["markets"][market][track]={
                "sessions":len(subset),"closed_trades":closed,
                "verified_pnl_trades":verified,
                "net_pnl_inr":round(sum(pnl),2) if pnl and track=="OPTION_BUY" else None,
                "index_points":round(sum(float(r.get("index_points") or 0) for r in subset),3)
                                if track=="INTRADAY" else None,
                "status":"INCOMPLETE" if len(subset)<5 or verified<closed and track=="OPTION_BUY" else "REPORTED",
            }
    dest=Path("trader/research/ema9_v2_weekly.json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2)+"\n")
    response=session.patch(base+"ema9_v2_weekly/"+start.isoformat(),
        json={"fields":{k:firestore_field(v) for k,v in report.items()}},timeout=30)
    response.raise_for_status()
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
