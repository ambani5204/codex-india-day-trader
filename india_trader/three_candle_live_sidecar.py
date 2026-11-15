"""Independent read-only 3 Candle Top Down CE/PE paper monitor.

Uses V2 index signal; fills options ONLY at observable live bid/ask.
Never calls an order endpoint. Persist daily journal and publish Firestore
independently of legacy paper dashboard.
"""
from __future__ import annotations
import datetime as dt,json,os,time
from pathlib import Path
from .core import IST
from .upstox import UpstoxReader,UpstoxError,INDICES,load_today_master,select_atm
from .three_candle_top_down_v2 import test_day
from .paper_sim import option_fees

OUT=Path("trader/three_candle_live")
def event(journal,**data):
    journal.write(json.dumps({"strategy":"THREE_CANDLE_TOP_DOWN_V2","mode":"PAPER_ONLY_NO_ORDERS",**data},default=str)+"\n")
    journal.flush()

def run():
    now=dt.datetime.now(IST)
    if now.weekday()>4 or now.time()>=dt.time(14,45):
        print("Outside market-day startup");return
    while dt.datetime.now(IST).time()<dt.time(9,15):
        time.sleep(5)
    if not os.environ.get("UPSTOX_ACCESS_TOKEN"):raise RuntimeError("Missing Upstox token")
    api=UpstoxReader();records=load_today_master("trader/upstox_instruments.json",now.date())
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/(now.date().isoformat()+".jsonl")
    if path.exists():raise RuntimeError("Existing top-down session journal; duplicate runner blocked")
    previous={};positions={};done=set()
    with path.open("x") as journal:
        while dt.datetime.now(IST).time()<dt.time(15,15):
            now=dt.datetime.now(IST)
            for market in ("NIFTY","SENSEX"):
                try:
                    allbars=api.candles(INDICES[market])
                    bars=sorted((b for b in allbars if b.time.date()==now.date() and b.time+dt.timedelta(minutes=5)<=now),
                                key=lambda b:b.time)
                    if not bars:continue
                    if market not in previous:
                        past=api.historical_index_candles(INDICES[market],now.date()-dt.timedelta(days=7),now.date()-dt.timedelta(days=1))
                        if not past:raise UpstoxError("No previous session")
                        d=max(b.time.date() for b in past)
                        previous[market]=[b for b in past if b.time.date()==d]
                    if market not in done and market not in positions:
                        status,signal,stages=test_day(bars,previous[market],market,now.date(),2.,live_prefix=True)
                        if status=="OPEN_SIGNAL":
                            signal_time=dt.datetime.fromisoformat(signal["entry_time"])
                            if 0<=(now-signal_time).total_seconds()<=90:
                                direction="BUY" if signal["side"]==1 else "SELL"
                                contract=select_atm(records,market,direction,bars[-1].close,now.date())
                                q=api.full_quote(contract["instrument_key"])
                                if abs((now-q.timestamp).total_seconds())>15 or q.ask<=0 or q.bid<=0 or q.ask_qty<contract["lot_size"]:
                                    event(journal,event="OPTION_ENTRY_BLOCKED",market=market,time=now.isoformat(),reason="STALE_OR_ILLIQUID_QUOTE")
                                else:
                                    positions[market]={"contract":contract,"entry":q.ask,"time":now.isoformat(),
                                        "index_stop":signal["stop"],"index_target":signal["target"],
                                        "side":signal["side"]}
                                    event(journal,event="OPTION_PAPER_OPEN",market=market,time=now.isoformat(),
                                          symbol=contract["symbol"],option_type=contract["option_type"],
                                          quantity=contract["lot_size"],entry_price=q.ask,
                                          index_stop=signal["stop"],index_target=signal["target"])
                                done.add(market)
                    if market in positions:
                        pos=positions[market];q=api.full_quote(pos["contract"]["instrument_key"])
                        if abs((now-q.timestamp).total_seconds())>15 or q.bid<=0 or q.bid_qty<pos["contract"]["lot_size"]:
                            event(journal,event="EXIT_QUOTE_UNAVAILABLE",market=market,time=now.isoformat())
                            continue
                        side=pos["side"];spot=bars[-1].close
                        stop=(spot<=pos["index_stop"] if side==1 else spot>=pos["index_stop"])
                        target=(spot>=pos["index_target"] if side==1 else spot<=pos["index_target"])
                        premium_stop=q.bid<=pos["entry"]*.85
                        premium_target=q.bid>=pos["entry"]*1.30
                        eod=now.time()>=dt.time(15,10)
                        if stop or target or premium_stop or premium_target or eod:
                            qty=pos["contract"]["lot_size"]
                            fee=option_fees(pos["entry"],q.bid,qty,pos["contract"]["exchange"],"UPSTOX")["total"]
                            event(journal,event="OPTION_PAPER_CLOSED",market=market,time=now.isoformat(),
                                  symbol=pos["contract"]["symbol"],quantity=qty,entry_price=pos["entry"],
                                  exit_price=q.bid,fees_inr=fee,
                                  net_pnl_inr=round((q.bid-pos["entry"])*qty-fee,2),
                                  reason="INDEX_STOP" if stop else "INDEX_TARGET" if target else
                                         "PREMIUM_STOP" if premium_stop else "PREMIUM_TARGET" if premium_target else "EOD")
                            del positions[market]
                except (UpstoxError,ValueError,KeyError) as exc:
                    event(journal,event="DATA_ERROR",market=market,time=now.isoformat(),reason=type(exc).__name__)
            time.sleep(25)
        for market,pos in positions.items():
            event(journal,event="UNRESOLVED_POSITION",market=market,time=dt.datetime.now(IST).isoformat(),
                  symbol=pos["contract"]["symbol"])
if __name__=="__main__":run()
