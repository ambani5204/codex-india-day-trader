"""Firestore publisher for separate three-candle CE/PE paper results."""
import datetime as dt,json,os
from pathlib import Path
from india_trader.core import IST
from deploy.nightly_strategy_evaluation import firestore_field

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    day=dt.datetime.now(IST).date().isoformat()
    journal=Path("trader/three_candle_live")/(day+".jsonl")
    if not journal.exists():raise RuntimeError("No three-candle journal")
    events=[json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session=AuthorizedSession(creds)
    base=f"https://firestore.googleapis.com/v1/projects/{os.environ['FIREBASE_PROJECT_ID']}/databases/(default)/documents/three_candle_paper/"
    for market in ("NIFTY","SENSEX"):
        rows=[x for x in events if x.get("market")==market]
        trades=[x for x in rows if x.get("event")=="OPTION_PAPER_CLOSED"]
        open_count=sum(x.get("event")=="OPTION_PAPER_OPEN" for x in rows)
        closed_count=len(trades)
        data={"date_ist":day,"market":market,"strategy":"THREE_CANDLE_TOP_DOWN_V2",
              "instrument":"CE_PE_OPTION_BUY","mode":"PAPER_ONLY_NO_ORDERS",
              "opened":open_count,"closed_trades":closed_count,
              "unresolved":sum(x.get("event")=="UNRESOLVED_POSITION" for x in rows),
              "data_errors":sum(x.get("event")=="DATA_ERROR" for x in rows),
              "net_pnl_inr":round(sum(x["net_pnl_inr"] for x in trades),2) if trades else None,
              "status":"NO_SESSION_DATA" if not rows else "PAPER_RECORDED",
              "source":"read_only_upstox_live_bid_ask"}
        resp=session.patch(base+day+"_"+market,json={"fields":{k:firestore_field(v) for k,v in data.items()}},timeout=30)
        resp.raise_for_status()
        print("PUBLISHED",day,market,closed_count)
if __name__=="__main__":main()
