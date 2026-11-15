"""Agent 2: EMA9 V2 index baseline plus strict stock/options data feasibility.

Do not represent index spot candle P&L as stock or options results.
"""
import argparse,datetime as dt,json
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions
from .index_intraday_backtest import _LazyHistoricalReader
from .ema9_fib_pivot_research import evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=364)
    sessions=_load_sessions(start,end,"BOTH",_LazyHistoricalReader(),"trader/backtest_cache")
    results={}
    for market in ("NIFTY","SENSEX"):
        r=evaluate([s for s in sessions if s["market"]==market])
        results[market]={k:v["metrics"] for k,v in r.items()}
    output={"kind":"EMA9_V2_AGENT2_RESEARCH","period":[str(start),str(end)],
            "index_spot_futures_proxy":results,
            "stock_universe":{"status":"NOT_TESTED","reason":
                "Existing historical reader explicitly rejects stock instrument keys; no point-in-time historical stock universe provided."},
            "historical_option_buying":{"status":"NOT_TESTED","net_pnl_inr":None,
                "reason":"Index candles do not provide historical option strike/expiry bid-ask premiums, fills or charges."},
            "paper_only":True,"real_orders":False}
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(output,indent=2))
if __name__=="__main__":main()
