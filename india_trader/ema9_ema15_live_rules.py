"""EMA9/EMA15 live index-signal engine; NO BROKER ORDERS.

Stop is the completed SIGNAL CANDLE high/low, never a capital percentage.
Index R levels govern exits; option bid/ask determines paper P&L separately.
"""
from __future__ import annotations
import datetime as dt
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class Signal:
    side: int
    signal_time: str
    entry_due: str
    signal_close: float
    candle_stop: float
    angle: float
    body_fraction: float

def detect(bars,angle_min=20.,body_min=.85):
    """Evaluate ONLY the last completed five-minute bar, no look-ahead."""
    if len(bars)<21:return None
    bars=sorted(bars,key=lambda b:b.time)
    e9=e15=bars[0].close
    atr=max(.01,bars[0].high-bars[0].low)
    prev9=e9
    for i,b in enumerate(bars[1:],1):
        prev9=e9
        e9+=(b.close-e9)*.2
        e15+=(b.close-e15)*.125
        prev=bars[i-1]
        tr=max(b.high-b.low,abs(b.high-prev.close),abs(b.low-prev.close))
        atr+=(tr-atr)/14
    b=bars[-1]
    if b.time.time()>=dt.time(14,30):return None
    rng=b.high-b.low
    if rng<=0 or atr<=0:return None
    body=abs(b.close-b.open)/rng
    angle=math.degrees(math.atan((e9-prev9)/atr))
    bull=e9>e15 and angle>=angle_min and b.close>b.open and body>=body_min and (b.high-b.close)/rng<=.1
    bear=e9<e15 and angle<=-angle_min and b.close<b.open and body>=body_min and (b.close-b.low)/rng<=.1
    if not (bull or bear):return None
    return Signal(1 if bull else -1,b.time.isoformat(),
                  (b.time+dt.timedelta(minutes=5)).isoformat(),
                  b.close,b.low if bull else b.high,round(angle,3),round(body,4))

def levels(signal,actual_index_entry):
    """Derive risk from candle extremes; reject invalid stop geometry."""
    risk=signal.side*(actual_index_entry-signal.candle_stop)
    if risk<=0:raise ValueError("Entry crossed signal candle stop")
    return {"entry":actual_index_entry,"stop":signal.candle_stop,
            "risk_points":risk,"t1":actual_index_entry+signal.side*2*risk,
            "t2":actual_index_entry+signal.side*3*risk,
            "trail_stop":actual_index_entry+signal.side*risk}

def advance(state,bar):
    """Conservative stop-first OHLC evaluation. Trail activates NEXT bar after T1."""
    side=state["side"]
    stop=state["trail_stop"] if state["t1_hit"] else state["stop"]
    if side*(bar.open-stop)<=0 or (bar.low<=stop if side==1 else bar.high>=stop):
        return "STOP",state
    if state["t1_hit"]:
        if (bar.high>=state["t2"] if side==1 else bar.low<=state["t2"]):
            return "TARGET_3R",state
    elif (bar.high>=state["t1"] if side==1 else bar.low<=state["t1"]):
        state={**state,"t1_hit":True}
        return "T1_REACHED",state
    return "OPEN",state
