"""Late NIFTY expiry reversal/rollover: independent research, NO live orders.

Uses 5-minute index OHLC as a direction-only proxy, NOT historical option
premiums. Expiry dates must be explicitly supplied and verified externally.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from .core import IST
from .research_optimizer import _load_sessions
from .index_intraday_backtest import _LazyHistoricalReader

WINDOW_START=dt.time(14,30)
WINDOW_END=dt.time(15,10)
FLAT=dt.time(15,15)

def candle_side(bar):
    return 1 if bar.close>bar.open else -1 if bar.close<bar.open else 0

def strong(bar, previous, min_body_ratio=.65, min_range_multiple=1.3):
    width=bar.high-bar.low
    if width<=0 or abs(bar.close-bar.open)/width<min_body_ratio:return False
    sample=[b.high-b.low for b in previous[-6:] if b.high>b.low]
    return bool(sample) and width>=min_range_multiple*(sum(sample)/len(sample))

def candidates(bars):
    """Signal only at close of complete 5m bar; 3 preceding opposing candles."""
    out=[]
    for i in range(3,len(bars)):
        b=bars[i]
        close=b.time+dt.timedelta(minutes=5)
        if not WINDOW_START<=close.time()<=WINDOW_END:continue
        direction=candle_side(b)
        if not direction or any(candle_side(x)!=-direction for x in bars[i-3:i]):continue
        if not strong(b,bars[max(0,i-6):i]):continue
        # Strong close near extreme; confirmation against previous candle.
        if direction==1 and not (b.close>bars[i-1].high and
                (b.high-b.close)/(b.high-b.low)<=.2):continue
        if direction==-1 and not (b.close<bars[i-1].low and
                (b.close-b.low)/(b.high-b.low)<=.2):continue
        out.append({"bar_index":i,"direction":direction,
                    "signal_time":close.isoformat(),"signal_close":b.close,
                    "signal_high":b.high,"signal_low":b.low})
    return out

def replay(bars,day,slippage=1.,rr=1.5):
    """One active index-point proxy; allow reversal on later opposite signal."""
    bars=sorted((b for b in bars if b.time.date()==day),key=lambda b:b.time)
    clock={b.time:b for b in bars}
    required=[dt.datetime.combine(day,dt.time(14,10),IST)+dt.timedelta(minutes=5*i)
              for i in range(14)]  # 14:10 through 15:15 inclusive
    if any(t not in clock for t in required):
        return {"status":"INCOMPLETE_CANDLES","trades":[],"signals":0}
    signals={x["bar_index"]:x for x in candidates(bars)}
    pos=None;trades=[];pending=None
    for i,b in enumerate(bars):
        if b.time.time()<dt.time(14,30):continue
        if b.time.time()>FLAT:break
        if pending is not None and b.time.time()<FLAT:
            s=pending;pending=None
            side=s["direction"];entry=b.open+side*slippage
            stop=s["signal_low"] if side==1 else s["signal_high"]
            risk=side*(entry-stop)
            if risk>0:
                pos={"entry":entry,"stop":stop,"target":entry+side*rr*risk,
                     "direction":side,"risk":risk,"entry_time":b.time.isoformat(),
                     "signal_time":s["signal_time"]}
        if pos is not None:
            side=pos["direction"]
            if b.time.time()>=FLAT:
                price=b.open-side*slippage;why="TIME_EXIT"
            else:
                gap_stop=(b.open<=pos["stop"] if side==1 else b.open>=pos["stop"])
                gap_target=(b.open>=pos["target"] if side==1 else b.open<=pos["target"])
                hit_stop=(b.low<=pos["stop"] if side==1 else b.high>=pos["stop"])
                hit_target=(b.high>=pos["target"] if side==1 else b.low<=pos["target"])
                if gap_stop:price=b.open-side*slippage;why="GAP_STOP"
                elif gap_target:price=b.open-side*slippage;why="GAP_TARGET"
                elif hit_stop:price=pos["stop"]-side*slippage;why="STOP_FIRST"
                elif hit_target:price=pos["target"]-side*slippage;why="TARGET"
                else:price=None;why=None
            if price is not None:
                points=side*(price-pos["entry"])
                trades.append({**pos,"exit":price,"exit_reason":why,
                               "exit_time":b.time.isoformat(),
                               "index_points":round(points,3),
                               "realized_r":round(points/pos["risk"],4)})
                pos=None
        s=signals.get(i)
        if s and b.time.time()<dt.time(15,10):
            if pos is None:
                pending=s
            elif s["direction"]!=pos["direction"]:
                # Opposite confirmed candle closes at next bar open: no lookahead.
                # Exit current position at next bar open, then enter opposite.
                if i+1<len(bars) and bars[i+1].time==b.time+dt.timedelta(minutes=5):
                    nxt=bars[i+1]
                    side=pos["direction"]
                    price=nxt.open-side*slippage
                    points=side*(price-pos["entry"])
                    trades.append({**pos,"exit":price,"exit_reason":"ROLLOVER",
                                   "exit_time":nxt.time.isoformat(),
                                   "index_points":round(points,3),
                                   "realized_r":round(points/pos["risk"],4)})
                    pos=None;pending=s
    return {"status":"OK" if pos is None and pending is None else "UNRESOLVED",
            "signals":len(signals),"trades":trades}

def load_expiries(path):
    if not path:return None
    with open(path,newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows or "date" not in rows[0]:
        raise ValueError("Expiry CSV requires date column")
    return {dt.date.fromisoformat(r["date"]) for r in rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=365)
    p.add_argument("--expiry-csv",help="Verified NIFTY expiry dates CSV with date column")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    if not 30<=a.days<=730:p.error("days must be 30..730")
    end=dt.datetime.now(IST).date()-dt.timedelta(days=1)
    start=end-dt.timedelta(days=a.days-1)
    expiries=load_expiries(a.expiry_csv)
    report={"strategy":"NIFTY_EXPIRY_REVERSAL_ROLLOVER_V1",
            "start":start.isoformat(),"end":end.isoformat(),
            "mode":"INDEX_DIRECTION_PROXY_ONLY","real_orders":False,
            "expiry_calendar_verified":expiries is not None,
            "status":"AWAITING_VERIFIED_EXPIRY_CALENDAR" if expiries is None else "PENDING_DATA",
            "warning":"No historical option premium, spreads, IV, theta, or expiry settlement modeled"}
    if expiries is not None:
        sessions=_load_sessions(start,end,"NIFTY",_LazyHistoricalReader(),"trader/backtest_cache")
        results=[replay(s["bars"],s["day"]) for s in sessions if s["day"] in expiries]
        trades=[t for r in results if r["status"]=="OK" for t in r["trades"]]
        wins=[t for t in trades if t["index_points"]>0]
        losses=[t for t in trades if t["index_points"]<0]
        report.update({"status":"INDEX_PROXY_RESEARCH_ONLY","expiry_sessions":len(results),
                       "complete_sessions":sum(r["status"]=="OK" for r in results),
                       "incomplete_sessions":sum(r["status"]!="OK" for r in results),
                       "signals":sum(r["signals"] for r in results),
                       "trades":len(trades),"wins":len(wins),"losses":len(losses),
                       "win_rate_pct":round(100*len(wins)/len(trades),2) if trades else None,
                       "net_index_points":round(sum(t["index_points"] for t in trades),2),
                       "total_r":round(sum(t["realized_r"] for t in trades),3),
                       "trade_details":trades})
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    print("EXPIRY_REVERSAL_RESEARCH",report["status"])
if __name__=="__main__":main()
