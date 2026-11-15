"""Read-only EMA9/15 CE/PE live paper runner. Never submits broker orders."""
from __future__ import annotations
import datetime as dt,json,os,time
from pathlib import Path
from .core import IST
from .upstox import UpstoxReader,UpstoxError,INDICES,load_today_master,select_atm
from .ema9_ema15_live_rules import detect,levels,advance
from .paper_sim import option_fees

OUT=Path("trader/ema9_ema15_live")
def emit(f,**event):
    f.write(json.dumps({"strategy":"EMA9_EMA15_20DEG_85BODY","mode":"PAPER_ONLY_NO_ORDERS",**event},default=str)+"\n")
    f.flush()

def run():
    now=dt.datetime.now(IST)
    if now.weekday()>4 or not dt.time(9,15)<=now.time()<dt.time(14,45):
        print("Outside market-hour startup; no paper session");return
    if not os.environ.get("UPSTOX_ACCESS_TOKEN"):raise RuntimeError("Missing read-only Upstox token")
    api=UpstoxReader()
    records=load_today_master("trader/upstox_instruments.json",now.date())
    OUT.mkdir(parents=True,exist_ok=True)
    journal=OUT/(str(now.date())+".jsonl")
    if journal.exists():raise RuntimeError("Duplicate session journal; refusing to restart")
    positions={};pending={};last_processed={};done=set()
    with journal.open("x") as f:
        while dt.datetime.now(IST).time()<dt.time(15,15):
            now=dt.datetime.now(IST)
            for market in ("NIFTY","SENSEX"):
                try:
                    raw=api.candles(INDICES[market])
                    bars=sorted((b for b in raw if b.time.date()==now.date() and b.time+dt.timedelta(minutes=5)<=now),key=lambda b:b.time)
                    if len(bars)<21:continue
                    latest=bars[-1]
                    # Process each completed bar exactly once; never look into the current bar.
                    if last_processed.get(market)==latest.time:continue
                    last_processed[market]=latest.time
                    if market in positions:
                        pos=positions[market]
                        event,state=advance(pos["index"],latest)
                        pos["index"]=state
                        if event=="T1_REACHED":
                            emit(f,event="INDEX_2R_CONFIRMED",market=market,time=now.isoformat(),symbol=pos["contract"]["symbol"])
                        if event in ("STOP","TARGET_3R") or now.time()>=dt.time(15,10):
                            q=api.full_quote(pos["contract"]["instrument_key"])
                            if abs((now-q.timestamp).total_seconds())>15 or q.bid<=0 or q.bid_qty<pos["quantity"]:
                                emit(f,event="EXIT_QUOTE_UNAVAILABLE",market=market,time=now.isoformat(),reason=event)
                            else:
                                fee=option_fees(pos["premium_entry"],q.bid,pos["quantity"],pos["contract"]["exchange"],"UPSTOX")["total"]
                                emit(f,event="OPTION_PAPER_CLOSED",market=market,time=now.isoformat(),symbol=pos["contract"]["symbol"],
                                     quantity=pos["quantity"],entry_price=pos["premium_entry"],exit_price=q.bid,fees_inr=fee,
                                     net_pnl_inr=round((q.bid-pos["premium_entry"])*pos["quantity"]-fee,2),reason=event if event!="OPEN" else "TIME_EXIT")
                                del positions[market]
                    if market in pending and market not in positions:
                        sig=pending.pop(market)
                        if market in done:continue
                        # Next bar open is not a tradable quote from completed candles.
                        # Use first observed live index snapshot after signal close, not synthetic open fill.
                        spot=latest.close
                        try: idx={**levels(sig,spot),"side":sig.side,"t1_hit":False}
                        except ValueError:
                            emit(f,event="ENTRY_BLOCKED",market=market,time=now.isoformat(),reason="INDEX_ENTRY_CROSSED_CANDLE_STOP")
                            done.add(market);continue
                        contract=select_atm(records,market,"BUY" if sig.side==1 else "SELL",spot,now.date())
                        q=api.full_quote(contract["instrument_key"])
                        qty=contract["lot_size"]
                        capital=float(os.getenv("EMA_PAPER_CAPITAL_INR","30000"))
                        max_spread=float(os.getenv("EMA_MAX_SPREAD_PCT","2"))
                        spread=200*(q.ask-q.bid)/(q.ask+q.bid) if q.ask+q.bid>0 else 999
                        if abs((now-q.timestamp).total_seconds())>15 or q.ask<=0 or q.bid<=0 or q.ask_qty<qty or q.bid_qty<qty or spread>max_spread or q.ask*qty>capital:
                            emit(f,event="ENTRY_BLOCKED",market=market,time=now.isoformat(),reason="STALE_ILLIQUID_WIDE_SPREAD_OR_INSUFFICIENT_CAPITAL",premium_outlay=q.ask*qty,capital_inr=capital)
                        else:
                            positions[market]={"contract":contract,"quantity":qty,"premium_entry":q.ask,"index":idx}
                            emit(f,event="OPTION_PAPER_OPEN",market=market,time=now.isoformat(),symbol=contract["symbol"],
                                 option_type=contract["option_type"],quantity=qty,entry_price=q.ask,premium_outlay=q.ask*qty,
                                 index_entry=spot,index_stop=idx["stop"],index_r=idx["risk_points"],index_t1=idx["t1"],index_t2=idx["t2"])
                        done.add(market)
                    if market not in done and market not in positions and market not in pending:
                        sig=detect(bars)
                        if sig:
                            pending[market]=sig
                            emit(f,event="INDEX_SIGNAL",market=market,time=now.isoformat(),direction="CE" if sig.side==1 else "PE",
                                 signal_time=sig.signal_time,signal_close=sig.signal_close,index_stop=sig.candle_stop,
                                 angle=sig.angle,body_fraction=sig.body_fraction)
                except (UpstoxError,ValueError,KeyError) as exc:
                    emit(f,event="DATA_ERROR",market=market,time=now.isoformat(),reason=type(exc).__name__)
            time.sleep(20)
        for market,pos in positions.items():
            emit(f,event="UNRESOLVED_POSITION",market=market,time=dt.datetime.now(IST).isoformat(),symbol=pos["contract"]["symbol"])
if __name__=="__main__":run()
