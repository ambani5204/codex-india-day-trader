# Indian-market 11-skill map — experimental all-day paper trading

**Source design:** [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
**Current project:** this repository; eleven Codex skill folders remain in `.agents/skills/`.
**Trading scope:** Indian NSE/BSE index signals, NFO/BFO **paper** option longs and hedged credit spreads; no live order submission.

The original skills are *independent capabilities*, not eleven autonomous trading agents which all run on every bar. The new all-day engine composes relevant capabilities; reporting "all 11 running in the trading loop" would be inaccurate.

| Skill | Indian adaptation | Automated in experimental paper-advanced? |
|---|---|---|
| trader-scanner | Scan closed 5-minute NIFTY/SENSEX for BREAKOUT / FAKEOUT / TRAP plus EMA 8/21 and mean reversion | Yes |
| trader-news | Indian macro/NSE/BSE headlines and exchange announcements with sources | No — separate manual RSS research; not an unverified auto-signal |
| trader-entry | Verified closed candle + Upstox actual option-chain Greeks/strike/expiry/spread/depth | Yes |
| trader-exit | Long-option stop/target/time exit; hedged spread credit stop/target/time exit | Yes — paper quote-based, not broker protected |
| trader-timemachine | Historical NIFTY/SENSEX backtesting/replay and walk-forward analysis | Offline/on-demand; NOT a validated full strategy backtest |
| trader-budget | Virtual premium allocation, lots and defined spread max-payoff-loss estimate | Yes, conservative estimated |
| trader-risk | Trade-loss and daily limits, cooldown, maximum trades, unresolved-session block | Yes; margin and settlement not certified |
| trader-broker | Strictly paper journal; no real orders, no actual fill | Yes — recorded hypothetical legs only |
| trader-alerts | REST quote polling while position is open for stop/target/time events | Yes internally; NOT reliable push alerts |
| trader-analyst | Earnings/financial disclosures for Indian listed companies | Manual CSV; not directly relevant to index option intraday signals |
| trader-pelosi | India analogue: publicly available SEBI/stock-exchange insider disclosures | Manual CSV; not an index-options intraday execution driver |

## Pure intraday chart replay (independent of CE/PE)

`bash backtest-index-intraday-year.sh` runs a **hypothetical index-direction backtest** using real cached (or downloaded) five-minute NIFTY/SENSEX candles. It reuses both `intraday_signal` and `index_stop_plan` from the advanced paper strategy, including BREAKOUT/FAKEOUT/TRAP/EMA/MEAN_REVERSION signals and technical stops/targets. Entries happen **only at the following five-minute OPEN**. Same-candle ambiguous target/stop hits conservatively exit at the stop; session gaps through a stop are priced at the adverse open; the session ends at 15:10. It enforces one open position, a 15-minute cooldown, three trades per market day and a minimum **1.5 gross chart R:R** at the actual next open.

The outcomes are **index points and normalized R units** with per-pattern win rate, profit factor and drawdown. They are **not hypothetical option premiums**, rupee trading returns, broker-executable index orders, or a credit-spread backtest. This is an appropriate first diagnostic of signal quality before later testing the additional option Greeks, IV/expiry, fees, fill uncertainty and hedged margin mechanics. An annual result must be compared out-of-sample to avoid overfitting pattern definitions.

## Three-way opening-range strategy (new advanced mode only)

The reference window is exactly **09:15–09:30 IST** (three completed 5-minute candles), and all classification is made from completed 5-minute bars with a 90-second freshness check; no historical future candles or intrabar breakouts. Both index direction and option side follow the signal:

| Pattern | Closed-candle evidence | Bullish option structure | Bearish option structure | Planned index stop / target |
|---|---|---|---|---|
| BREAKOUT | First full candle CLOSES beyond high/low with a small range buffer | Buy CE or sell hedged PE credit | Buy PE or sell hedged CE credit | Breakout candle extreme or OR boundary retest; target projected 2R |
| FAKEOUT | Wick sweeps high/low, candle closes back inside and rejects the move, no earlier breakout close | Lower sweep → CE / hedged PE credit | Upper sweep → PE / hedged CE credit | Beyond actual wick extreme; target OR midpoint |
| TRAP | Actual 1–3 previous candle CLOSES beyond opening range then current bar CLOSES back inside | Failed downside close → CE / hedged PE credit | Failed upside close → PE / hedged CE credit | Beyond failed breakout episode extreme; target opposite range boundary |

Candidate structures use separate expected payoffs. A **net R:R >= 1.5** is required for buying options and **net target/credit-stop R:R >= 0.25** for hedged credits. A high ratio alone cannot certify profitability. Higher-IV credit selling is *only a candidate regime heuristic*, not an empirically established edge. The same-day expiry short-credit entry cutoff remains **13:45 IST**; bought CE/PE always use the first eligible future expiry. Minimum lots, real available depth, fees, slippage, adaptive percentage equity budget, daily loss allowance and stale quote guards remain in force; zero trades is a valid result.

The last available annual index replay from 1 October 2025 through 1 October 2026 predated this three-pattern change; **the prior counts and absent option P&L are NOT a backtest of this updated strategy**. New test coverage includes fakeout versus trap, reversal direction, no lookahead, structural stops/targets, selection priority and next-expiry contracts. All executions are hypothetical.

## Opt-in test on Android

**Do not change a running session in the middle of the day or if a previous position is unresolved.** Stop the old Termux scheduler with CTRL+C outside market hours, then:

```bash
cd ~/codex-india-day-trader
git pull
python -m unittest discover -s tests -v
PAPER_MODE=advanced bash live-paper-android.sh
```

The launcher reuses a validated locally saved Upstox Analytics Token. It waits for the next weekday at 09:15 IST and selects Mon/Tue/Fri NIFTY, Wed/Thu SENSEX. It uses REST snapshots about every 30 seconds, looks for **new 5-minute close signals** between 09:35 and 14:40 IST, monitors existing paper positions, and can take multiple paper trades **up to configured daily limits** (typically three) if valid. A cooldown of 15 minutes follows each closed trade. A day with no signals or no qualifying contracts must result in **zero trades**.

**Experimental IV and setup playbook:** When chain IV is below 18% the engine considers a long CE/PE. Above that exploratory threshold, BREAKOUT/TRAP/EMA favor a long CE/PE first, and FAKEOUT/MEAN_REVERSION favor a defined-risk hedged credit spread first; the other eligible structure is tried only when its own fee-adjusted risk, expiry and quote rules pass. Breakout trades go with the breached side; fakeout and trap reverse the failed side. The threshold is illustrative, not calibrated, not a predictor of profit. On a Sensex expiry day, the short spread may use the current expiry but targets a **14:45 IST** modeled exit; long options continue to exclude same-day expiry by default. Long options seek a time exit by 15:10. If quote delivery fails near an exit, the journal records **UNRESOLVED**; there is no fictional fill. Stops are not guaranteed.

**A credit spread is NOT naked option selling.** Bullish => sell OTM put + buy lower-strike put; bearish => sell OTM call + buy higher-strike call. Both legs use live bid/ask/quantity and the same expiry. Theoretical maximum loss at expiry is spread width less credit, plus estimated charges, but executable prices, early unwind losses, actual margin, penalties and exchange settlement are **not** verified. We do not recommend copying paper positions directly into a live brokerage order.

The experimental engine does not use 1-year historical option Greeks, independently confirmed IV percentiles, synchronized two-leg execution, an exchange-calibrated 5-level hedge book, exchange holiday scheduling, margin API checks, true spread/slippage distributions or a verified backtest of these trade rules. Before interpreting paper profit, collect and independently replay *actual timestamped NFO/BFO options quotes* and model missed trades, non-fills, brokerage, fees, settlement and drawdowns. Do not call these results an established trading edge.

**Legacy ORB remains the default** and works via:
```bash
bash live-paper-android.sh
```
Only `PAPER_MODE=advanced` enables the new all-day route. Neither mode submits real broker orders.
