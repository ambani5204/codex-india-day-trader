"""Research-only 5-minute index mean-reversion walk-forward; never places orders.

Usage: python -m deploy.mean_reversion_365d --nifty nifty_5m.csv --sensex sensex_5m.csv
CSV format: timestamp/open/high/low/close (or date). Prices are INDEX proxy,
NOT executable CE/PE prices. Requires 365 calendar days of historical coverage.
"""
import argparse
import datetime as dt
import itertools
import json
from collections import defaultdict
from statistics import mean, pstdev
from india_trader.core import read_bars

def evaluate_day(bars, z, trend, rr, cost_bps):
    """One closed-candle signal/day; enter next bar OPEN, stop-first intrabar."""
    bars = sorted(bars, key=lambda b: b.time)
    if len(bars) < 12:
        return None
    closes = [b.close for b in bars]
    lookback = min(20, max(8, int(60 / max(1, (bars[1].time-bars[0].time).total_seconds()/60))))
    for i in range(lookback, len(bars)-1):
        bar, previous = bars[i], bars[i-1]
        if not (dt.time(10, 0) <= bar.time.time() < dt.time(13, 30)):
            continue
        reference = closes[i-lookback:i]
        avg, sigma = mean(reference), pstdev(reference)
        if sigma <= 0:
            continue
        fast = mean(closes[i-max(3,lookback//3):i+1])
        slow = mean(closes[i-lookback:i+1])
        if abs(fast/slow-1) > trend:
            continue
        direction = (1 if previous.close < avg-z*sigma and bar.close > previous.close and bar.close < avg
                     else -1 if previous.close > avg+z*sigma and bar.close < previous.close and bar.close > avg
                     else 0)
        if not direction:
            continue
        entry_bar = bars[i+1]
        entry = entry_bar.open
        stop = bar.low if direction == 1 else bar.high
        risk = direction*(entry-stop)
        if risk <= 0 or risk/entry > .015 or risk/entry < .0002:
            continue
        # Require an actual reversal close with a meaningful body, not merely a one-tick bounce.
        body = abs(bar.close-bar.open)
        full_range = bar.high-bar.low
        if full_range <= 0 or body/full_range < .35:
            continue
        # Avoid entry after an excessive rebound; preserve room to the mean.
        if direction*(avg-entry) < 1.25*risk:
            continue
        target = entry + direction*risk*rr
        exit_price = bars[-1].close
        reason = "TIME"
        for future in bars[i+1:]:
            stop_hit = future.low <= stop if direction == 1 else future.high >= stop
            target_hit = future.high >= target if direction == 1 else future.low <= target
            if stop_hit:
                exit_price, reason = (min(future.open,stop) if direction==1 else max(future.open,stop)), "STOP"
                break
            if target_hit:
                exit_price, reason = target, "TARGET"
                break
        net_r = (direction*(exit_price-entry) - entry*cost_bps/10000)/risk
        return {"date":str(bar.time.date()),"direction":direction,"entry":entry,
                "stop":stop,"target":target,"exit":exit_price,"reason":reason,
                "net_r":round(net_r,6)}
    return None

def summarize(trades):
    wins = sum(t["net_r"] > 0 for t in trades)
    profit = sum(max(0,t["net_r"]) for t in trades)
    loss = -sum(min(0,t["net_r"]) for t in trades)
    equity = peak = max_dd = 0.
    for trade in trades:
        equity += trade["net_r"]
        peak = max(peak,equity)
        max_dd = max(max_dd,peak-equity)
    return {"trades":len(trades),"wins":wins,
            "win_rate_pct":round(100*wins/len(trades),2) if trades else None,
            "net_r":round(equity,3),
            "profit_factor":round(profit/loss,3) if loss else None,
            "max_drawdown_r":round(max_dd,3)}

def run(path, cost_bps):
    bars = read_bars(path)
    if not bars:
        raise ValueError("No historical bars")
    dates = sorted({b.time.date() for b in bars})
    coverage = (dates[-1]-dates[0]).days
    if coverage < 364:
        raise ValueError(f"365-day coverage required; got {coverage+1} calendar days")
    by_day = defaultdict(list)
    for bar in bars:
        by_day[bar.time.date()].append(bar)
    # Chronological 70/30 split. No test-period parameter selection.
    split = max(1,int(len(dates)*.7))
    train_dates, test_dates = dates[:split], dates[split:]
    candidates = []
    for z,trend,rr in itertools.product((1.5,2.,2.5),(0.001,0.0025,0.005),(1.,1.5,2.,3.)):
        def trades(days):
            return [trade for d in days if (trade:=evaluate_day(by_day[d],z,trend,rr,cost_bps))]
        training = trades(train_dates)
        stats = summarize(training)
        # Reject tiny sample sizes and zero-risk fabricated profitability.
        if stats["trades"] < 25:
            continue
        candidates.append((stats["net_r"],stats["trades"],z,trend,rr,stats))
    if not candidates:
        return {"status":"INSUFFICIENT_TRAINING_TRADES","calendar_days":coverage+1}
    _,_,z,trend,rr,training = max(candidates)
    test_trades = [trade for d in test_dates if (trade:=evaluate_day(by_day[d],z,trend,rr,cost_bps))]
    holdout = summarize(test_trades)
    qualified = (holdout["trades"] >= 20 and holdout["win_rate_pct"] is not None
                 and holdout["win_rate_pct"] >= 60 and holdout["net_r"] > 0
                 and holdout["profit_factor"] is not None and holdout["profit_factor"] > 1)
    return {"status":"INDEX_PROXY_ONLY","calendar_days":coverage+1,
            "sessions":len(dates),"train_sessions":len(train_dates),
            "holdout_sessions":len(test_dates),
            "selected":{"z":z,"max_trend_divergence":trend,"reward_risk":rr},
            "training":training,"holdout":holdout,"passes_proxy_gate":qualified,
            "warning":"Index-price proxy only. No historical option-chain prices, lot sizes, option brokerage, spreads or actual option fills. Do not deploy on this result."}


def resample(bars, minutes):
    if minutes == 1:
        return bars
    from india_trader.core import Bar
    groups=defaultdict(list)
    for b in bars:
        offset=b.time.hour*60+b.time.minute-555
        if 0<=offset<375:
            groups[(b.time.date(),offset//minutes)].append(b)
    output=[]
    for _,seq in sorted(groups.items()):
        seq.sort(key=lambda b:b.time)
        if len(seq)!=minutes:
            continue
        output.append(Bar(seq[0].time,seq[0].open,max(x.high for x in seq),
                          min(x.low for x in seq),seq[-1].close,sum(x.volume for x in seq)))
    return output

def matrix(path,cost_bps):
    raw=read_bars(path)
    dates=sorted({b.time.date() for b in raw})
    if not dates or (dates[-1]-dates[0]).days<364:
        raise ValueError("365-day genuine 1-minute historical coverage required")
    results={}
    split=max(1,int(len(dates)*.7))
    for minutes in (1,3,5,10,15,30):
        by_day=defaultdict(list)
        for b in resample(raw,minutes):
            by_day[b.time.date()].append(b)
        for rr in (1.,1.5,2.,3.):
            candidates=[]
            for z,trend in itertools.product((1.5,2.,2.5),(.001,.0025,.005)):
                trades=[t for d in dates[:split] if (t:=evaluate_day(by_day[d],z,trend,rr,cost_bps))]
                stats=summarize(trades)
                if stats["trades"]>=15:
                    candidates.append((stats["net_r"],stats["trades"],z,trend))
            key=str(minutes)+"m_RR_"+str(rr)
            if not candidates:
                results[key]={"status":"INSUFFICIENT_TRAINING_TRADES","holdout":summarize([])}
                continue
            _,_,z,trend=max(candidates)
            trades=[t for d in dates[split:] if (t:=evaluate_day(by_day[d],z,trend,rr,cost_bps))]
            results[key]={"status":"INDEX_PROXY_ONLY","timeframe_minutes":minutes,
                          "reward_risk":rr,"stop_rule":"signal_candle_high_low",
                          "selected":{"z":z,"trend":trend},"holdout":summarize(trades)}
    return {"sessions":len(dates),"calendar_days":(dates[-1]-dates[0]).days+1,
            "combinations":results}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nifty",required=True)
    parser.add_argument("--sensex",required=True)
    parser.add_argument("--cost-bps",type=float,default=10.)
    parser.add_argument("--output",default="mean_reversion_365d_results.json")
    args = parser.parse_args()
    if args.cost_bps < 0:
        parser.error("cost-bps must be nonnegative")
    results = {"kind":"MEAN_REVERSION_365D_MULTI_TIMEFRAME_INDEX_PROXY",
               "NIFTY":matrix(args.nifty,args.cost_bps),
               "SENSEX":matrix(args.sensex,args.cost_bps)}
    with open(args.output,"w",encoding="utf-8") as f:
        json.dump(results,f,indent=2)
    print(json.dumps(results,indent=2))

if __name__ == "__main__":
    main()
