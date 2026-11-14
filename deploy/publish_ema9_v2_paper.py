"""Publish separate EMA9 V2 paper results without overwriting legacy dashboard."""
import datetime as dt
import json
import os
from pathlib import Path
from india_trader.core import IST
from deploy.nightly_strategy_evaluation import firestore_field

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    today=dt.datetime.now(IST).date().isoformat()
    path=Path("trader/ema9_v2_live")/(today+".jsonl")
    if not path.exists():raise RuntimeError("No EMA9 paper journal")
    rows=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session=AuthorizedSession(creds)
    base=("https://firestore.googleapis.com/v1/projects/"+os.environ["FIREBASE_PROJECT_ID"]+
          "/databases/(default)/documents/ema9_v2_paper/")
    for market in ("NIFTY","SENSEX"):
        subset=[x for x in rows if x.get("market")==market]
        for track in ("OPTION_BUY","INTRADAY"):
            trades=[x for x in subset if x.get("track")==track and x.get("event")=="PAPER_TRADE_CLOSED"]
            verified=[x for x in trades if isinstance(x.get("net_pnl_inr"),(int,float))]
            data={"date_ist":today,"market":market,"track":track,"strategy":"EMA9_FIB_V2",
                  "mode":"PAPER_ONLY_NO_BROKER_ORDERS","closed_trades":len(trades),
                  "verified_pnl_trades":len(verified),
                  "net_pnl_inr":round(sum(x["net_pnl_inr"] for x in verified),2) if verified else None,
                  "index_points":round(sum(x.get("index_points",0) for x in trades),3) if track=="INTRADAY" else None,
                  "unresolved":sum(x.get("event")=="UNRESOLVED_POSITION" and x.get("track")==track for x in subset),
                  "status":"INCOMPLETE" if not subset else "PAPER_RECORDED"}
            name=f"{today}_{market}_{track}"
            resp=session.patch(base+name,json={"fields":{k:firestore_field(v) for k,v in data.items()}},timeout=30)
            resp.raise_for_status()
            print("PUBLISHED",name,data["closed_trades"])
if __name__=="__main__":main()
