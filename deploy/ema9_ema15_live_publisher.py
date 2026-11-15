"""Continuously publish EMA9/15 read-only option paper journal."""
import datetime as dt,time
from india_trader.core import IST
from deploy.publish_ema9_ema15_paper import main
def run():
    while dt.datetime.now(IST).time()<dt.time(15,20):
        try:main()
        except Exception as exc:print("EMA_PUBLISH_ERROR",type(exc).__name__,str(exc)[:180],flush=True)
        time.sleep(60)
if __name__=="__main__":run()
