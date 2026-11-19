"""Export genuine Upstox index OHLC for isolated Mean Reversion research."""
import argparse
import csv
import datetime as dt
from pathlib import Path
from india_trader.core import IST
from india_trader.historical_backtest import load_historical_index
from india_trader.index_intraday_backtest import _LazyHistoricalReader

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=365)
    p.add_argument("--out-dir",default="research_data")
    args=p.parse_args()
    if args.days<365 or args.days>730:
        p.error("days must be 365..730")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=args.days-1)
    out=Path(args.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    reader=_LazyHistoricalReader()
    for market in ("NIFTY","SENSEX"):
        bars=load_historical_index(reader,market,start,end,"trader/backtest_cache")
        bars=sorted((b for b in bars if start<=b.time.date()<=end),key=lambda b:b.time)
        if not bars:
            raise RuntimeError(f"{market}: no genuine historical bars returned")
        dates={b.time.date() for b in bars}
        coverage=(max(dates)-min(dates)).days+1
        if coverage<365:
            raise RuntimeError(f"{market}: insufficient actual coverage {coverage} days; need >=365")
        path=out/f"{market.lower()}_5m.csv"
        with path.open("w",newline="") as f:
            w=csv.writer(f)
            w.writerow(("timestamp","open","high","low","close","volume"))
            for b in bars:
                w.writerow((b.time.isoformat(),b.open,b.high,b.low,b.close,b.volume))
        print(f"{market}: {len(bars)} genuine candles, {len(dates)} sessions, {coverage} calendar-day coverage")
if __name__=="__main__":
    main()
