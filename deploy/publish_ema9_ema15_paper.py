"""Publish read-only EMA9/15 paper summaries to isolated Firestore collection."""
import datetime as dt,json,os
from pathlib import Path
from india_trader.core import IST
from deploy.nightly_strategy_evaluation import firestore_field

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    day=str(dt.datetime.now(IST).date())
    path=Path("trader/ema9_ema15_live")/(day+".jsonl")
    if not path.exists():return
    events=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    client=AuthorizedSession(creds)
    base=f"https://firestore.googleapis.com/v1/projects/{os.environ['FIREBASE_PROJECT_ID']}/databases/(default)/documents/ema9_ema15_paper/"
    for market in ("NIFTY","SENSEX"):
        rows=[e for e in events if e.get("market")==market]
        closed=[e for e in rows if e.get("event")=="OPTION_PAPER_CLOSED"]
        opened=sum(e.get("event")=="OPTION_PAPER_OPEN" for e in rows)
        last=rows[-1] if rows else {}
        fields={"date_ist":day,"market":market,"strategy":"EMA9_EMA15_20DEG_85BODY",
                "mode":"PAPER_ONLY_NO_ORDERS","status":"PAPER_RECORDED" if rows else "NO_SESSION_DATA",
                "opened":opened,"closed_trades":len(closed),
                "open_positions":max(0,opened-len(closed)),
                "net_pnl_inr":round(sum(e["net_pnl_inr"] for e in closed),2) if closed else None,
                "last_event":last.get("event"),"last_event_time":last.get("time"),
                "last_symbol":last.get("symbol"),"index_stop":last.get("index_stop"),
                "data_errors":sum(e.get("event")=="DATA_ERROR" for e in rows),
                "source":"read_only_upstox_option_bid_ask"}
        response=client.patch(base+day+"_"+market,json={"fields":{k:firestore_field(v) for k,v in fields.items()}},timeout=30)
        response.raise_for_status()
        print("EMA_PUBLISHED",market,len(closed),flush=True)
if __name__=="__main__":main()
