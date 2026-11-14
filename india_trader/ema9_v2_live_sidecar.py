"""Independent EMA9 Fibonacci V2 live paper sidecar. No broker order API.

Both markets, option-buying and index-point intraday paper positions.
Never modifies existing strategy journals or the existing dashboard/latest.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import time
from pathlib import Path
from .core import IST
from .upstox import INDICES, UpstoxReader, UpstoxError, select_atm, load_today_master
from .ema9_fib_pivot_research import signals
from .paper_sim import option_fees

OUT=Path("trader/ema9_v2_live")
def run_market(market, api, records, now, positions, finished, events, prior_cache):
    day=now.date()
    bars=sorted((b for b in api.candles(INDICES[market]) if b.time.date()==day
                 and b.time+dt.timedelta(minutes=5)<=now),key=lambda b:b.time)
    if not bars:return
    if market not in prior_cache:
        prior_cache[market]=sorted((b for b in api.historical_index_candles(INDICES[market],
                  day-dt.timedelta(days=7),day-dt.timedelta(days=1)) if b.time.date()<day),
                key=lambda b:b.time)
    prev=prior_cache[market]
    # Upstox intraday endpoint may omit previous session; no guessed pivots.
    if not prev:
        events.append({"market":market,"event":"PREVIOUS_SESSION_UNAVAILABLE","time":now.isoformat()})
        return
    last_day=prev[-1].time.date()
    prior=[b for b in prev if b.time.date()==last_day]
    if not prior:return
    signal=signals(bars,prior,rr=3.0)
    if signal and market not in finished and not any(k[0]==market for k in positions):
        s=signal[0]
        t=dt.datetime.fromisoformat(s["signal_time"])
        if 0<=(now-t).total_seconds()<=90:
            direction=s["direction"]
            positions[(market,"INTRADAY")]={"signal":s,"entry":bars[-1].close,
                "time":now.isoformat(),"direction":direction}
            events.append({"event":"INDEX_PAPER_OPEN","market":market,"time":now.isoformat(),
                           "strategy":"EMA9_FIB_V2","track":"INTRADAY","signal":s,
                           "index_point_proxy":True})
            try:
                contract=select_atm(records,market,"BUY" if direction=="BULL" else "SELL",
                                    bars[-1].close,day)
                q=api.full_quote(contract["instrument_key"])
                if (now-q.timestamp).total_seconds()<=15 and q.ask>0 and q.bid>0 and q.ask_qty>=contract["lot_size"]:
                    positions[(market,"OPTION_BUY")]={"signal":s,"contract":contract,
                        "entry":q.ask,"direction":direction,"time":now.isoformat()}
                    events.append({"event":"OPTION_PAPER_OPEN","market":market,"time":now.isoformat(),
                                   "track":"OPTION_BUY","strategy":"EMA9_FIB_V2",
                                   "symbol":contract["symbol"],"premium":q.ask})
            except (UpstoxError,ValueError,KeyError) as exc:
                events.append({"event":"OPTION_ENTRY_BLOCKED","market":market,
                               "time":now.isoformat(),"reason":type(exc).__name__})
            finished.add(market)
    for track in ("INTRADAY","OPTION_BUY"):
        key=(market,track)
        if key not in positions:continue
        pos=positions[key];s=pos["signal"];bull=pos["direction"]=="BULL"
        index_stop=bars[-1].close<=s["stop"] if bull else bars[-1].close>=s["stop"]
        index_target=bars[-1].close>=s["target"] if bull else bars[-1].close<=s["target"]
        eod=now.time()>=dt.time(15,10)
        if track=="INTRADAY":
            if not (index_stop or index_target or eod):continue
            points=(bars[-1].close-pos["entry"])*(1 if bull else -1)
            events.append({"event":"PAPER_TRADE_CLOSED","market":market,"track":track,
                           "strategy":"EMA9_FIB_V2","time":now.isoformat(),
                           "index_points":round(points,3),"net_pnl_inr":None,
                           "reason":"INDEX_STOP" if index_stop else "INDEX_TARGET" if index_target else "EOD",
                           "warning":"Non-tradable index-point proxy; no INR P&L"})
            del positions[key]
        else:
            try:
                q=api.full_quote(pos["contract"]["instrument_key"])
                if (now-q.timestamp).total_seconds()>15 or q.bid<=0 or q.bid_qty<pos["contract"]["lot_size"]:
                    continue
                # Option premium stop/target independent of index chart stop.
                option_stop=q.bid<=pos["entry"]*.85
                option_target=q.bid>=pos["entry"]*1.30
                if not (option_stop or option_target or index_stop or index_target or eod):continue
                qty=pos["contract"]["lot_size"]
                fees=option_fees(pos["entry"],q.bid,qty,pos["contract"]["exchange"],"UPSTOX")
                net=round((q.bid-pos["entry"])*qty-fees["total"],2)
                events.append({"event":"PAPER_TRADE_CLOSED","market":market,"track":track,
                               "strategy":"EMA9_FIB_V2","time":now.isoformat(),
                               "symbol":pos["contract"]["symbol"],"quantity":qty,
                               "entry_price":pos["entry"],"exit_price":q.bid,
                               "fees_inr":fees["total"],"net_pnl_inr":net,
                               "reason":"OPTION_STOP" if option_stop else "OPTION_TARGET" if option_target else "INDEX_EXIT_OR_EOD",
                               "simulated":True})
                del positions[key]
            except (UpstoxError,ValueError,KeyError):
                continue

def main():
    now=dt.datetime.now(IST)
    if now.weekday()>4 or not dt.time(9,15)<=now.time()<dt.time(12,0):
        print("No valid start window");return
    OUT.mkdir(parents=True,exist_ok=True)
    if not os.getenv("UPSTOX_ACCESS_TOKEN"):raise RuntimeError("Missing Upstox token")
    from .upstox import load_today_master
    records=load_today_master("trader/upstox_instruments.json",now.date())
    api=UpstoxReader()
    positions={};finished=set();events=[];prior_cache={}
    path=OUT/(now.date().isoformat()+".jsonl")
    # A duplicate runner must not generate duplicate paper fills.
    if path.exists():raise RuntimeError("EMA9 V2 sidecar already started today")
    with path.open("x") as journal:
        while dt.datetime.now(IST).time()<dt.time(15,10):
            now=dt.datetime.now(IST)
            for market in ("NIFTY","SENSEX"):
                try:run_market(market,api,records,now,positions,finished,events,prior_cache)
                except (UpstoxError,ValueError,KeyError) as exc:
                    events.append({"event":"DATA_ERROR","market":market,"time":now.isoformat(),
                                   "reason":type(exc).__name__})
            for e in events:journal.write(json.dumps(e,default=str)+"\n")
            journal.flush();events.clear()
            time.sleep(25)
        for (market,track),pos in positions.items():
            journal.write(json.dumps({"event":"UNRESOLVED_POSITION","market":market,
                "track":track,"time":dt.datetime.now(IST).isoformat()})+"\n")
        journal.flush()

if __name__=="__main__":
    main()
