"""Nightly EMA9/15 research audit (index-price proxy only; no broker orders)."""
import datetime as dt,json
from pathlib import Path
from india_trader.core import IST
from india_trader.research_optimizer import _load_sessions
from india_trader.index_intraday_backtest import _LazyHistoricalReader
from india_trader.ema9_ema15_robustness_v2 import evaluate,summarize

def main():
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=89)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    out={"strategy":"EMA9_EMA15_CANDLE_STOP","mode":"RESEARCH_ONLY_NO_ORDERS",
         "start":str(start),"end":str(end),
         "warning":"Index futures-cost proxy, NOT option-premium backtest or actual option ROI",
         "results":{}}
    for market in ("NIFTY","SENSEX"):
        for angle in (15,20,25,30):
            for body in (.75,.80,.85,.90):
                trades=[]
                for session in sessions:
                    if session["market"]!=market or not session["bars"]:continue
                    t,_=evaluate(session["bars"],market,session["day"],angle=angle,body_min=body,
                                 entry_mode="next_open",stop_mode="after_t1")
                    if t:trades.append(t)
                out["results"][f"{market}_{angle}_{body}"]=summarize(trades)
    path=Path("trader/backtests/ema9_ema15_nightly.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"end":str(end),"configurations":len(out["results"])}))
if __name__=="__main__":main()
