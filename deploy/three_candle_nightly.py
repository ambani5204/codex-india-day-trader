"""Nightly index-signal audit, separate from real option paper fills."""
import datetime as dt,json,os
from pathlib import Path
from india_trader.core import IST
from india_trader.research_optimizer import _load_sessions
from india_trader.index_intraday_backtest import _LazyHistoricalReader
from india_trader.three_candle_top_down_v2 import test_day
from deploy.nightly_strategy_evaluation import firestore_field

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    day=dt.datetime.now(IST).date()
    sessions=_load_sessions(day-dt.timedelta(days=8),day,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    client=AuthorizedSession(creds)
    base=f"https://firestore.googleapis.com/v1/projects/{os.environ['FIREBASE_PROJECT_ID']}/databases/(default)/documents/three_candle_nightly/"
    out={"date_ist":str(day),"strategy":"THREE_CANDLE_TOP_DOWN_V2","markets":{}}
    for market in ("NIFTY","SENSEX"):
        rows=sorted((s for s in sessions if s["market"]==market and s["bars"]),key=lambda s:s["day"])
        cur=next((s for s in rows if s["day"]==day),None)
        prev=next((s for s in reversed(rows) if s["day"]<day),None)
        if cur and prev:
            status,trade,stages=test_day(cur["bars"],prev["bars"],market,day,2.)
            info={"date_ist":str(day),"market":market,"strategy":"THREE_CANDLE_TOP_DOWN_V2",
                  "mode":"INDEX_SIGNAL_AUDIT_NOT_OPTION_PNL","status":status,
                  "daily_sweep_reclaim":stages["daily_sweep_reclaim"],
                  "hourly_rejection":stages["hourly_rejection"],
                  "displacement_order_block":stages["displacement_order_block"],
                  "valid_retest_entry":stages["valid_retest_entry"],
                  "signal_executed_in_index_proxy":bool(trade),
                  "index_proxy_points":trade["index_points"] if trade else None,
                  "option_net_pnl_inr":None}
        else:
            info={"date_ist":str(day),"market":market,"strategy":"THREE_CANDLE_TOP_DOWN_V2",
                  "mode":"INDEX_SIGNAL_AUDIT_NOT_OPTION_PNL","status":"NO_COMPLETE_MARKET_SESSION",
                  "option_net_pnl_inr":None}
        out["markets"][market]=info
        resp=client.patch(base+str(day)+"_"+market,json={"fields":{k:firestore_field(v) for k,v in info.items()}},timeout=30)
        resp.raise_for_status()
        print("NIGHTLY_PUBLISHED",market,info["status"])
    path=Path("trader/backtests/three_candle_nightly.json")
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2)+"\n")
if __name__=="__main__":main()
