"""Periodic Firestore publication of isolated three-candle paper events."""
import datetime as dt,time
from pathlib import Path
from india_trader.core import IST
from deploy.publish_three_candle_paper import main
def run():
    day=dt.datetime.now(IST).date().isoformat()
    path=Path("trader/three_candle_live")/(day+".jsonl")
    while dt.datetime.now(IST).time()<dt.time(15,20):
        if path.exists():
            try:main()
            except Exception as exc:print("PUBLISH_ERROR",type(exc).__name__,str(exc)[:180],flush=True)
        time.sleep(60)
if __name__=="__main__":run()
