# Codex Day Trader — India edition (NIFTY / SENSEX / Upstox / Zerodha / Android)

**Status: read-only market-data/paper simulation. The original offline suite passed previously; newly added SQLite/server code includes offline tests but has NOT been verified with a live Upstox account or deployed on a VPS. NO live order execution.**

This project adapts the 11 skill *roles* from [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for **OpenAI Codex** in `.agents/skills/`. It is not the original repo's code ported line-for-line. For the original upstream Claude skill files and Python scripts, see [Import original files](#import-original-upstream-files-optional).

It is intended for **educational analysis** and controlled manual/paper workflows, not guaranteed profitability. Historical tests have lookahead and selection-bias risk unless verified against accurate, timestamped, independently collected market data.

## Simple strategy research before considering larger position sizes

The 96-configuration chart research run **failed** its validation gates on 1 Oct 2025–1 Oct 2026. Its attractive EMA-only rows had just 1–5 validation trades, insufficient to claim a repeatable edge. Rather than keep tuning dozens of combinations on the same seen historical dates, `research-simple-year.sh` compares **four fixed rules** only: **trend-confirmed 15-minute opening-range break** (1.5R or 2R) and **EMA8/21 trend continuation** (1.5R or 2R). There is no fakeout, trap or mean-reversion trading in this simple research branch.

```bash
cd ~/codex-india-day-trader
git pull
bash research-simple-year.sh
```

The new script reuses the existing Upstox index candle cache. It caps hypothetical entries at **one per day**, requires sufficiently directional price movement using closed-candle price efficiency, avoids compressed opening ranges, rejects weak directional candles, and applies an **entry-time cutoff** of 10:45 IST for ORB and 13:30 IST for EMA. The known-entry futures transaction fee proxy must cost **no more than 25% of the structural 1R risk**; a gross-good trade with disproportionately large taxes/charges is skipped *before* the simulated entry. All results are adjusted for one adverse chart-point of slippage each side plus date-aware estimated one-lot futures charges.

Results: `trader/backtests/simple_edge_2025-10-01_to_2026-10-01.json`. Each configuration must pass chronological **training and validation**, with enough trades, positive fee-adjusted average R, profit factor >= 1.10 and drawdown checks; one selected candidate then faces the final segment plus double-slippage sensitivity. **The historical 2025–26 holdout has already been inspected during prior optimization, so it is NOT a pristine unseen test of newly designed strategies.** Subsequent forward paper execution on executable futures/options must be independently verified. If no candidate passes, status is `NO_SIMPLE_STRATEGY_PASSED_VALIDATION`; there is NO automatic retry with relaxed thresholds and no promotion to active paper positions.

**Do not scale based on a chart proxy.** The gate `safe_to_scale=false` is unconditional: larger lots require real instrument-specific contract data, margin, depth/slippage capacity analysis, actual cost/tax calculation, and a fresh sample of independent forward paper trades across varied market conditions. Scaling magnifies adverse market moves and may deteriorate fill prices. Never equate more lots with an improvement in expected profit per contract.

## Research engine: trend, sideways, multiple R:R and transaction-tax sensitivity

The original one-year chart test (1 Oct 2025–1 Oct 2026) returned **602 paper index-point trades, a 32.23% win rate, −39.92R and 0.90 gross R profit factor**. It was **negative even before any tradable-instrument fees**. This is the BASELINE, not evidence of a profitable strategy. The new **standalone research optimizer** does not modify the saved paper-trading engine or automatically deploy new parameters.

From Android Termux with the historical index 5-minute candle cache already downloaded:

```bash
cd ~/codex-india-day-trader
git pull
bash research-index-year.sh
```

Or run a shorter bounded smoke test:

```bash
python tools/india.py research-index-walk-forward \
  --from-date 2025-10-01 --to-date 2026-10-01 \
  --market AUTO --max-configs 12 --slippage-points 1 \
  --out trader/backtests/index_research_smoke.json
```

The full local run evaluates **at most 96 predefined configurations**, spanning strategy baskets (all signals, directional, breakout+EMA, EMA alone), efficient versus choppy index-price movement, strong directional candle body, and **1.5R / 2R / 2.5R trend targets** with **minimum 1.2 or 1.5 chart R:R**. Opening-range width is also checked against bar ranges. These are based **only on candles known as of signal confirmation**. There is no look-ahead day label such as "this day eventually became sideways." A sideways day may be identified too late to prevent its first trade; this cannot be known ahead of time.

The optimizer uses a **chronological 60% training / 20% validation / 20% final holdout split**, a one-index-point-per-side adverse **hypothetical slippage assumption**, a maximum of three chart trades per day, stop-first resolution when a candle hits both stop and target, and a **historically dated futures-style transaction COST PROXY** including brokerage, STT, GST, SEBI charges, stamp duty, exchange and IPFT. The futures STT sell-side rate is **0.02% through 31 Mar 2026 and 0.05% from 1 Apr 2026**. NIFTY lot size changes are approximated 75→65 from January 2026, SENSEX 20; these are **not historical contract-by-contract fills**. Sources: [NSE futures STT](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax), [Upstox brokerage/charges](https://upstox.com/brokerage-charges/), [NIFTY lot circular](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf).

Every candidate must satisfy **positive estimated net average R, estimated net profit factor ≥1.05, sufficient training/validation observations, and drawdown gates**, and the *selected* candidate must also pass the held-out segment and **2 points of adverse slippage per side** stress. If no candidate passes, the correct result is **`NO_CANDIDATE_PASSED_TRAIN_AND_VALIDATION`**, never a manufactured winning parameter set. Other possible status: `HOLDOUT_OR_SLIPPAGE_STRESS_FAILED`; a passed gate is `RESEARCH_GATE_PASSED_HYPOTHETICAL_PROXY_ONLY`, not proof of profitable execution or permission to deploy. Historical re-optimization on the same dates can overfit even these gates.

**Cost-model limitation:** A NIFTY/SENSEX spot index cannot be traded. Its OHLC is not futures OHLC, so modeling *futures-like* fees using spot prices cannot establish actual futures **or options** after-fee profit. Real futures basis, bid-ask, margin/funding costs, historical active-contract lot changes, market impact, and **personal income tax** are not validated; these charges are only explicit sensitivity estimates.

### Nightly prospective monitoring and ONE human-review Issue

[**GitHub Actions: Nightly frozen ORB/EMA forward research**](.github/workflows/nightly-index-strategy-research.yml) is configured for **23:00 IST, Monday–Friday**, subject to GitHub scheduling delays. It starts comparing the **four already-frozen simple hypotheses only on fully completed days from 13 November 2026 onward**; it does not shift previously inspected 2025–2026 dates into a fictitious new holdout. New data is obtained from Upstox historical 5-minute **index** candles, and previously fetched segments are reused from the GitHub Actions cache. At 23:00, the runner deliberately analyzes through **yesterday IST** so it cannot treat the current day's partial/late historical response as complete.

The workflow runs all offline tests before data analysis. The `india_trader.forward_monitor` computes, separately for the ORB and EMA 1.5R/2R playbooks, completed-session coverage, first rejecting filter, normalized net R with the *futures-fee proxy*, adverse-slippage stress and drawdown. An evidence-review flag requires **at least 40 complete post-freeze sessions, at least 30 hypothetical chart trades for a candidate, at least 80% coverage, positive net average R, fee-adjusted profit factor ≥ 1.10 and the same checks under 2 points of adverse slippage per side**. Even passing these conditions creates **only a research hypothesis for human review**, never authorization to trade or scale. Four candidates on accumulating days are not four independent statistically conclusive tests.

Every completed job posts its JSON report and the suggested investigations as a 30-day downloadable Actions artifact. Every **Monday scheduled run**, or any manually dispatched run, updates **one existing GitHub Issue**: [Research review Issue #1](https://github.com/ambani5204/codex-india-day-trader/issues/1). It presents the observed evidence and specific questions to investigate; it does **not** automatically edit paper options code, trade instruments, place broker orders, create code-changing PRs, relax stops, increase lots or treat any review comment as deployment approval. Repo workflow permissions are limited to **read-only contents plus Issue write**, without source-code write permissions.

**Required one-time private setup:** In `Settings → Secrets and variables → Actions → New repository secret`, name the secret `UPSTOX_ACCESS_TOKEN` and insert your existing **read-only Upstox Analytics Token**. Official Upstox documentation describes a **one-year validity** for Analytics Tokens, which support historical market-data GETs without daily OAuth. Use the existing token rather than regenerating another, because only one Analytics Token is active per Upstox account. **Never enter it in a GitHub issue, README, code commit, chat message or workflow log.** The GitHub runner cannot access the phone's saved local token. If the secret is absent/invalid, the nightly run produces an explicit **NOT_RUN / DATA_UNAVAILABLE** artifact and fails instead of reporting fake trades.

Click the workflow in **Actions → Nightly frozen ORB and EMA forward research → Run workflow** to test after adding the secret. Check its artifact and [review issue](https://github.com/ambani5204/codex-india-day-trader/issues/1). In public inactive repositories GitHub may suspend scheduled workflows after 60 days without activity; confirm the workflow remains enabled. This monitoring process does **not** make real options/futures after-tax profits verifiable: spot index candles are non-tradable and the one-lot futures brokerage/STT/GST calculation is only a cost sensitivity proxy.

## Index-only intraday strategy test — NO options or put/call

Use this when you want to validate whether the three opening-range patterns (BREAKOUT, FAKEOUT, TRAP) and the unchanged EMA/mean-reversion setups have predictive value **on the 5-minute NIFTY/SENSEX chart itself**, without option chains, expiry selection, theta, spreads, Greeks, or broker orders.

```bash
cd ~/codex-india-day-trader
git pull
bash backtest-index-intraday-year.sh
```

This uses the existing `trader/backtest_cache` downloaded by `backtest-year.sh` for **1 Oct 2025 through 1 Oct 2026** (and downloads only missing chunks with your saved private Upstox Analytics Token). It follows the existing weekday schedule: Mon/Tue/Fri NIFTY, Wed/Thu SENSEX. Results include **WIN/LOSS**, **win rate**, **profit factor in normalized risk units**, **total/average R**, **max drawdown in R**, **chart points**, and **separate results for each of the five patterns**, monthly and by index.

**Exact methodology:**
- Same `intraday_signal` and `index_stop_plan` functions as the advanced paper worker. Confirm the signal only after a closed five-minute bar, enter at the **NEXT** bar's historical **OPEN** (not the signal close).
- Require a valid structural stop and target and at least **1.5:1 gross chart-price R:R calculated using the NEXT open**; skip if a gap makes the setup invalid or the target too near. One simulated directional position at a time, maximum three entries per market day and 15 minutes of cooldown after a closed trade.
- Check each subsequent five-minute bar high/low. If stop and target are both within one candle, assume **stop first**. A gap through the stop is exited at the adverse next bar **open**. Exit open trades at **15:10 IST** using that bar's open. Refuse incomplete days, including missing exit bars.
- Default assumed index slippage is **0 points**, because the untradeable index has no executable bid/ask. To stress-test: `INDEX_SLIPPAGE_POINTS=1 bash backtest-index-intraday-year.sh`. This arbitrarily subtracts 1 index point per side and must **NOT** be interpreted as realistic futures/options execution cost.

The complete journal is saved to `trader/backtests/index_intraday_2025-10-01_to_2026-10-01.json`. The terminal shows summary results; the JSON contains every hypothetical signal, exit, outcome, month, market and any excluded session.

**Important:** NIFTY and SENSEX *indices themselves are not tradable*. This is chart-only research, **not** a cash equities, futures or options trading backtest. There are **no INR profits or commission/margin assumptions**; aggregate NIFTY and SENSEX raw point totals are intentionally not summed. A profitable index-direction test does **not** establish a profitable CE/PE strategy: option premiums also depend on delta/gamma, IV, theta, spread, taxes and fill prices.

## Historical replay: 1 October 2025 – 1 October 2026

On Android Termux **outside market hours**:

```bash
cd ~/codex-india-day-trader
git pull
bash backtest-year.sh
```

This command loads the **saved private Upstox Analytics Token** and fetches actual V3 historical 5-minute NIFTY/SENSEX index candles in short API date chunks. Data is cached in `trader/backtest_cache` for reproducibility, and a full JSON signal report is saved to `trader/backtests/index_signals_2025-10-01_to_2026-10-01.json`. The final terminal message includes the candidate-signal counts, days with missing/incomplete candles and per-strategy breakdown.

The replay calls **the same** `india_trader.intraday_lab.intraday_signal` function used by the experimental `paper-advanced` session. It follows the weekday schedule Mon/Tue/Fri NIFTY, Wed/Thu SENSEX and uses only fully closed 5-minute candles available at each historical instant. If essential historical candles are missing, days are flagged rather than filled with fictitious data.

**Important: This is NOT an options P&L backtest and does not calculate a win rate.** Historical index candles cannot reconstruct option deltas, IV, bid-ask spread, executable order-book depth, strikes, expiries and both legs of a sold credit spread. Likewise it does not model the actual open-position cooldown or capital usage, so candidate signals are not executed trades. The precise real-time buying/selling selection engine cannot be replayed without market-time option-chain snapshots that standard historical index candles do not supply.

Upstox's **Expired Instruments API** can retrieve past option OHLC, but is plan-gated (Upstox Plus); historical OHLC alone is still not an actual bid/ask/Greeks snapshot. A full *approximate* options backtest would need an independently verified historical options dataset and explicit fill/Greek/IV estimation assumptions; it must be labeled approximate, not "same exact fills." Never report fabricated historical option profits.

Official historical API docs: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/ and https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/

### New opening-range playbook: BREAKOUT, FAKEOUT and TRAP

`PAPER_MODE=advanced` now distinguishes three **fully closed** 5-minute candle events against the opening 09:15–09:30 IST high/low:

| Event | Confirmation | Reversal or continuation direction | Index stop | Projected target |
|---|---|---|---|---|
| **BREAKOUT** | First bar CLOSES above opening high / below low with a range buffer | Continuation: above → BULL; below → BEAR | Breakout bar's extreme, or OR boundary retest | 2R index move (hypothetical) |
| **FAKEOUT** | Wick sweeps outside OR, rejects the move and closes back **inside** without previous outside close | Contrarian: upper sweep → BEAR; lower sweep → BULL | Beyond actual swept wick | OR midpoint |
| **TRAP** | 1–3 earlier bars CLOSED outside OR; newest bar closes back INSIDE | Contrarian: trapped bulls → BEAR; trapped bears → BULL | Beyond whole failed-breakout episode's extreme | Opposite OR boundary |

The pattern must remain recent; an old multi-candle trend returning to the range is not automatically labeled a trap. Ambiguous both-side wick sweeps produce no fakeout signal. The scanner requires fully closed bars and ignores stale 5-minute signals. EMA 8/21 and mean-reversion signals remain active alongside these patterns.

**Expiry-aware option decision:** BULL → buy CE or **sell PE + buy a lower-strike protective PE**; BEAR → buy PE or **sell CE + buy a higher-strike protective CE**. The buying leg comes from the **earliest eligible future expiry** (never expiring today). A credit spread uses same-expiry legs and is *never naked*; if its expiry is today, new entries are blocked after 13:45 IST.

**Buy vs sell preference (experimental, not validated):** If near-ATM IV is below 18%, evaluate only a long CE/PE. At or above 18%, directional **BREAKOUT, TRAP and EMA** consider long CE/PE first; range **FAKEOUT and MEAN_REVERSION** consider hedged credit first. If the preferred structure is rejected due to inadequate modeled R:R, risk, option depth or expiry cutoff, consider the second *only if independently eligible*. Long buys must offer at least **1.5 net R:R** including estimated charges; hedged credits require at least **0.25 net target-to-credit-stop R:R**, with positive target net profit and both credit-stop plus expiry maximum payoff loss inside the adaptive equity-risk allowance. These ratios are **not directly comparable** across option buying and credit selling because their outcome distributions differ. No trade is guaranteed. Quote/API outages fail closed.

All live trading is disabled: this is a *read-only, quote-based paper simulator*. Historical 2025–26 signal counts were generated **before** this new classification and are **not** a backtest of the new signals or historical option profits.

### New option risk controls in `PAPER_MODE=advanced`

The Indian options adaptation now follows the **exit → budget → risk** design of the original US toolkit:

**Updated advanced risk budget:** In `PAPER_MODE=advanced`, the risk cap is **1.0% of current paper equity** by default (₹1,000 at ₹1,00,000 equity), **or the remaining daily loss allowance, whichever is less**. Edit `advanced_risk_percent` in `trader/config.json` to select **0.1%–1.0%**; e.g. 0.75 = 0.75%. Trade loss estimates include fees and adverse assumed slippage. This is a *paper-only risk-budget experiment*, not a recommendation to risk 1% live. The legacy `paper-upstox` ORB keeps `max_loss_per_trade_inr=500`. The existing maximum daily loss ₹1,500 and max three daily trades are unchanged. Higher reward/risk does **not** waive the percentage budget or make an invalid stop acceptable.
- **Strategy-specific long option stop:** ORB tests the breakout high/low with a volatility buffer; if the entire confirmed breakout candle lies beyond that boundary, its own low/high is the invalidation point. An EMA 8/21 crossover uses the latest **six-candle swing extreme** plus a **0.2 × ATR(14)** buffer, and rejects entries extended more than 2.5 ATR from that stop. Mean reversion uses the **last three bars' extreme**, also buffered by 0.2 ATR. The ATR uses only completed five-minute index bars. An index stop is mapped to an **indicative** option bid using live option delta, and the index invalidation is checked on completed bars (not ticks).
- **Strategy-specific target and position size:** ORB and EMA use a planned **2R index-price projection**; mean reversion targets the **previous 20-bar mean**, matching the signal logic. The target is mapped to an indicative option bid using current delta; **advanced mode no longer assumes an arbitrary 30% option-premium target**. Current Upstox CE/PE bid/ask and displayed depth, delta 0.40–0.65, whole current exchange lots (up to three), estimated 5 bps adverse slippage and fees determine whether net expected reward/risk is at least **1.5**. This is a filter, not a forecast. Unaffordable full lots and net-negative/poor-reward setups are **skipped**, never forced with an artificially tight stop. The worker rechecks all limits after a delayed estimated fill.
- **Credit spreads:** Never naked. A sold OTM CE/PE must be hedged with a farther-OTM same-expiry long leg. Both **spread width minus received credit plus estimated four-leg fees** AND **the planned buy-to-close credit-stop loss including fees** must independently fit the **advanced percentage-of-equity budget** (or the smaller remaining daily allowance). An estimated target/stop **net reward-to-risk of at least 0.25** is required, with a strictly positive estimated target profit; this differs from the 1.5 long-buy threshold because payoff distributions differ. Expiry-day new spread entries are blocked after 13:45 IST, with a time-exit target by 14:45. The index stop can trigger an earlier paper exit.
- **Daily protection:** Max modeled risk **1% of current paper equity per advanced trade (default)**, max modeled cumulative **₹1,500 loss** and at most **three closed trades** per session day, with a 15-minute cooldown. A winning trade does **not** restore a previously consumed daily loss budget. If an exit quote is missing, no fictitious fill is recorded; an unresolved position blocks future sessions.

This is **forward paper research**, not broker execution. Market jumps and stale/polled REST data can cause actual losses beyond the planned stop. Index delta is only a first-order approximation, and the code does not verify broker margin, actual hedge execution order, fill certainty or guaranteed spread close-out. None of the 2025–2026 index-only historical candidate signals is evidence of profitable option fills.

### High-IV structure selection and safely rejected alternatives (paper only)

The advanced mode uses a **setup-specific structure priority**, not a blanket requirement to sell whenever IV is high. With chain IV at least 18%, opening-range **BREAKOUT/TRAP and EMA** first examine a non-expiring bought CE/PE, whereas **FAKEOUT and MEAN_REVERSION** first examine a fully hedged credit spread. If the first **eligibility screen** fails, the second structure is considered under its own *expiry, liquidity, fees, net reward:risk, complete-lot and remaining-day budget* requirements. On same-day expiry, a new short spread is always blocked after 13:45 IST. A missing quote or transport failure is **not** an invitation to switch structures or manufacture a paper fill.

An ineligible option structure is journaled as `STRUCTURE_REJECTED`, with a specific reason and an indicated alternative (`TRY_NON_EXPIRING_LONG_OPTION` or `TRY_HEDGED_CREDIT_SPREAD`); final failures record `SIGNAL_REJECTED`. `OPTION_SELECTION` is still **not a fill**; only `PAPER_BUY_FILLED` counts as a completed long-option entry, and `PAPER_SPREAD_OPEN` represents a hypothetical two-leg spread. `paper-diagnose` reports abandoned structures separately. IV crush, theta and missed quote fills may still defeat a long-option trade despite an apparently favorable delta-mapped target.

The Nov 12, 2026 SENSEX log contained **9 index signals but zero fills**, with **6 rejections** after the expiry-day short-spread cutoff and **3** credit-spread screening rejections. Thus it does not establish that the stop loss alone was wrong. It predates the fallback and subsequent risk/stop improvements and cannot retroactively show the performance of the new engine.

### Diagnose why SENSEX/NIFTY paper entries were skipped

A session with zero trades does not prove a stop-loss caused the rejection. Using a **second Termux session**, read your existing simulation journals without calling any broker API:

```bash
cd ~/codex-india-day-trader
python tools/india.py paper-diagnose --date 2026-11-12 --market SENSEX
```

Look at `signals`, `rejections`, `recent_risk_plans`, and `closed_trades`. If no index signals were detected, the stop price was not even evaluated. `SIGNAL_REJECTED` messages identify the actual filter, including no favorable structural target, lack of minimum net reward/risk, insufficient option depth, or full-lot loss over the active adaptive budget. Open sessions appear as `pending_or_unresolved_sessions`; this is normal until the worker has finished and written a session summary.

The documented stop/target refinements affect **new** `PAPER_MODE=advanced` processes started after `git pull`. They do not retroactively modify prior journal records or the preceding year's index-only candidate-signal report. New trading signals stop at 14:40 IST; open positions may be monitored later. Keep the running worker until the session completes unless diagnosing a safe shutdown outside market hours.

## EXPERIMENTAL: All-session options paper trading (buy and hedged sell)

This new option is **not the default**: the older ORB-only system is retained unchanged unless you opt in.

Stop the existing overnight Termux scheduler with CTRL+C **outside market hours and only if no unresolved paper position**, then:

```bash
cd ~/codex-india-day-trader
git pull
python -m unittest discover -s tests -v
PAPER_MODE=advanced bash live-paper-android.sh
```

This checks the saved Analytics Token and schedules the next weekday. From 09:35 until 14:40 IST, it evaluates new **closed 5-minute** index bars for opening-range breakout, fakeout, bull/bear trap, EMA crossover or mean-reversion setups. With qualifying Upstox option-chain quotes, it may paper-buy a CE/PE, or paper-sell a **defined-risk credit spread with a mandatory long wing**. It monitors positions approximately every 30 seconds through REST snapshots and may record several trades per day, but only while original loss/capital/daily trade limits permit. **No setups or failed filters means zero trades.** IV >= 18% is an *experimental*, non-validated decision threshold, not a reliable option-selling signal.

Same-day expiry short spreads are **paper-only** and seek a modeled exit by 14:45 IST; long option paper positions seek a 15:10 time exit. If quotes disappear, any position stays **UNRESOLVED** and blocks a new simulated session. There are no real fills, exchange orders, protective broker stops, confirmed four-leg simultaneous execution, or verified spread margin. Commissions and taxes are estimates. Use this solely to collect forward data and examine whether *net* results survive conservative cost assumptions; no profitable edge has been established.

**All eleven original skill names remain** in `.agents/skills`, but not every skill participates in each intraday decision. See [actual Indian 11-skill integration status](docs/INDIA_11_SKILLS.md) for details. In particular, company earnings, insider filings, news and historical backtesting have separate workflows and must not be mislabeled as active auto-trade signals. A fresh, independently validated options tick/backtest dataset is needed before treating this experiment as a strategy.

## Android overnight start (no VPS required)

**Start at any time** — night, morning, or during market hours. In Termux:

```bash
cd ~/codex-india-day-trader
git pull
bash start-anytime.sh
```

Enter a **new private** Upstox Analytics Token **once** in Termux (input is hidden).
The launcher verifies read-only market-data access before waiting, requests an Android CPU wake lock, starts the local read-only dashboard at `http://127.0.0.1:8080`, and stays running until you stop it. It does not store your token in the database.

* Start **before 09:15 IST**: waits for the next weekday at 09:15.
* Start **09:15–15:10 IST**: begins that day's market session now. The strategy can consider only fresh, confirmed signals; **no missed signals or fills are invented**.
* Start **after 15:10 IST** or on a weekend: waits until the next market weekday at 09:15.
* Weekday plan: Mon/Tue/Fri NIFTY; Wed/Thu SENSEX. **Exchange holidays not yet checked**.
* The first potential ORB entry is **after 09:35**, not at 09:20. On completion, the process remains running and waits for the next trading weekday automatically. Results are saved incrementally to `trader/paper.sqlite3` and detailed journals stay in `trader/paper_upstox/`.
* **Important**: Turn on Android Settings → Apps → Termux → Battery → Unrestricted, leave Termux active, keep the phone charged, connected to the internet, and do not reboot/force-stop. Android may still kill background apps or suspend network access; **an overnight start is best-effort, not guaranteed**. Use a VPS for reliable unattended operation.
* No actual trades or broker orders are submitted.

Check the local dashboard for **Waiting for NIFTY/SENSEX** before sleeping. Stop with **CTRL+C** in Termux. If it gets killed, start the command again; duplicate same-day paper sessions are blocked.

## Persistent daily/monthly results and always-on hosting

The Upstox Android dashboard archives paper sessions to durable **SQLite** at `trader/paper.sqlite3`; full quote/event journals remain on disk in `trader/paper_upstox/`. **Closing Termux does not delete files** unless app data/storage is removed.

```bash
cd ~/codex-india-day-trader
git pull
python tools/india.py db-sync
python tools/india.py db-report --period day
python tools/india.py db-report --period month
```

For **automatic 09:15 weekday starts**, run on an always-on Linux VPS, not a phone. The complete one-time setup is in **[deploy/README.md](deploy/README.md)** with `bash deploy/install_server.sh`, systemd background services and private Tailscale HTTPS access from Android. An Upstox Analytics Token is read-only and valid for **one year** (not daily), unless revoked. No VPS or remote dashboard has been deployed by this repository update. This is still unverified against live Upstox market data.

## NEW — Upstox + Android mobile dashboard (2026-11-11)

**For someone without a brokerage/API subscription:** you can run the dashboard with explicitly labeled **synthetic demonstration** journals. This proves software behavior and charge accounting, NOT that the trading strategy makes money.

This upgrade provides a **read-only Upstox V3 REST** quote adapter. It is **snapshot polling**, not tick-by-tick WebSocket streaming. Upstox OAuth, account login, and actual quote delivery require your own account/API access and have **NOT been tested live** here. Indian index options remain strictly paper only: no order endpoint is present. The existing 11 Codex skill files and original Kite commands remain intact.

### Try demo without any broker account (Windows / VS Code)

```powershell
py -3 -m unittest discover -s tests -v
py -3 tools/india.py demo-generate
py -3 tools/india.py dashboard --mode demo --host 127.0.0.1 --port 8080
```

On the **same device**, open `http://127.0.0.1:8080` in Chrome. The demo shows both a profitable and a losing *invented* options trade with estimated Upstox basic brokerage, STT, GST, exchange transaction fees, SEBI, IPFT and stamp duty. You must **not** extrapolate these invented prices to real win rate or profitability.

### Demo directly on Android (Termux)

1. Install a trusted Termux distribution (e.g. F-Droid) and download/extract the ZIP. Keep `.agents` and all source folders. In Termux install `python` and `unzip`, then `cd` to the extracted project folder.
2. Run `python tools/india.py demo-generate` and `python tools/india.py dashboard --mode demo --host 127.0.0.1 --port 8080`.
3. Open **Chrome on that same Android phone**: `http://127.0.0.1:8080`.

This is a *local* demo; Android can suspend Termux when the phone sleeps. It is **not** an always-on cloud service and does not fetch live market data without an Upstox account.

### Android AUTO: weekday market and option contract selection

The default Android launcher now chooses the paper market automatically:

| Day | Paper market | Regular weekly expiry |
| --- | --- | --- |
| Monday | NIFTY | Tuesday |
| Tuesday | NIFTY | Tuesday |
| Wednesday | SENSEX | Thursday |
| Thursday | SENSEX | Thursday |
| Friday | NIFTY | Following Tuesday |

This is a **fixed user-requested schedule**, not proof of higher returns. Holidays are not yet checked automatically. Daily start remains manual.

Run in Termux:

```bash
cd ~/codex-india-day-trader
git pull
bash live-paper-android.sh
```

Press **Enter** for AUTO, then provide a new Upstox token **in Termux only**. The worker checks for a newly confirmed index ORB, requests the current Upstox option chain and selects a real contract with absolute delta **0.40–0.65**, targeting **0.50**. Entry also requires a quoted premium within virtual capital and risk budgets, a narrow bid/ask spread and enough visible depth. Missing Greeks/market depth or a rejected limit means **NO TRADE**, not a made-up fill. The mobile session card displays the selected strike, expiry, delta and ask premium.

**Expiry safety:** This simulator intentionally avoids **same-day expiry** contracts. On Tuesday it selects an eligible later NIFTY expiry; on Thursday a later SENSEX expiry. Exercise/settlement and expiry-specific closing auction risks are not implemented. Upstox access/Greeks are not verified with a live account and snapshots do not guarantee executions.

### Android: NIFTY and SENSEX together (manual daily start)

After installing Python and cloning this project in Termux:

```bash
cd ~/codex-india-day-trader
git pull
bash live-paper-android.sh
```

Choose **BOTH** (press Enter for default) to start two independent workers, or choose NIFTY/SENSEX alone. One current Upstox token is entered **locally, hidden on screen**; do not post it in chat or commit it. For BOTH, the launcher splits configured virtual capital and risk limits equally between the two markets. The dashboard at `http://127.0.0.1:8080` combines the two paper journals. No broker orders are sent.

Run the launcher **each market day around 09:15-09:30 IST**. It does not self-start the next day and cannot reliably keep running while Android suspends Termux. Each market worker stops on a closed paper trade, rejected entry, missed/stale signal, market data error, or the session cutoff (by 15:25 IST); the dashboard remains open until interrupted. It does **not** execute a trade on every day. Standard Upstox access tokens generally expire at 03:30 IST the following morning; renew through official Upstox authentication, subject to the token type and API entitlement. An exchange holiday calendar is not implemented.

This is REST snapshot polling (not tick-by-tick) and has not yet been verified with live account credentials. Simulated net P&L is not guaranteed realizable performance.

### Live forward PAPER trading when you have Upstox credentials

1. Create an Upstox trading account and developer app if your API entitlement permits; follow the [official OAuth flow](https://upstox.com/developer/api-documentation/authentication/). **Do not send the client secret or access token in chat.**
2. Create `trader/config.json` from `trader/config.example.json`, setting `"allow_derivatives": true`, keeping `"paper": true` and `"allow_live_orders": false`. This only enables paper analysis.
3. Store today's access token in the process environment (PowerShell example): `$env:UPSTOX_ACCESS_TOKEN = '<token obtained from official OAuth locally>'`. Do not commit credentials.
4. Download the **public** current-day Upstox master and start a session *before the first 09:35 closed 5-minute candle or immediately after it*, on a real Indian trading day:

   ```powershell
   py -3 tools/india.py upstox-sync
   py -3 tools/india.py paper-upstox --market NIFTY --lots 1 --fee-profile UPSTOX
   # Or use: --market SENSEX
   ```

5. In another terminal, start the mobile dashboard:

   ```powershell
   py -3 tools/india.py dashboard --mode upstox --host 127.0.0.1 --port 8080
   ```

`paper-upstox` waits for a **newly observed, fully closed** 5-minute opening-range breakout, deterministically selects the nearest *non-expiring-day* ATM CE or PE from today's exchange master, obtains the **actual option quote depth**, and simulates orders with bid/ask, depth, modeled adverse slippage and nonzero latency. It has stale-data guards, per-trade and daily risk limits, no duplicate-day sessions, and does not manufacture a closing fill if real-time data disappears. Data cannot be backfilled as a fictional live trade. The CLI `--fee-profile ZERODHA` alternative models Zerodha's schedule while using Upstox *market data*; the default models Upstox Basic, not Upstox Plus.

**Important limits:** REST quotes are not exchange executions, no websocket tick data, no full depth queue-position modeling or partial fills, missed 5-second price moves, no actual broker contract note, no overnight exercise/expiry settlement, penalties, margin/contract-specific rules, holiday check, or automatic post-disconnection position resolution. The simulation cannot determine *exact* realizable profit; it can estimate net profitability under stated costs and adverse fill assumptions. Never evaluate demo P&L as a strategy edge. Broker fee schedules change; cross-check before meaningful interpretation.

**Daily token renewal:** Upstox access tokens expire at **3:30 AM IST the next day** according to [Upstox documentation](https://upstox.com/developer/api-documentation/get-token/). An always-online dashboard can run continuously, but **the live feed requires user-authorized daily renewal**. We have not implemented automated OAuth reauthorization. If token renewal fails the simulation pauses/fails rather than inventing quotes or fills.

### Cloud server / Android browser setup

After provisioning your own Linux VPS with Docker and a domain:

1. Copy this project to the server. Set `DASHBOARD_USERNAME` and a random 16+ character `DASHBOARD_PASSWORD` in a **private** local `.env` beside `compose.yaml`. Keep it out of git. Do not paste API keys into chat.
2. Run `docker compose up -d --build dashboard`. This exposes port 8080 **only to server localhost**. Configure a TLS reverse proxy (e.g. Caddy/Nginx) with HTTPS and DNS pointing your own domain to the server. Never publish an unencrypted Basic-Auth dashboard directly to the internet.
3. You can log in from Android Chrome to `https://your-domain.example` using the dashboard credentials. It is read-only; the host doesn't control or connect to your phone.
4. For live market data, renew the Upstox token through the provider's secure login flow, set `UPSTOX_ACCESS_TOKEN` securely in the worker environment, run `docker compose --profile paper run --rm paper_worker python tools/india.py upstox-sync` (instrument master) and then `docker compose --profile paper run --rm paper_worker` before the open. Both share `trader/` journals with the dashboard.
5. The cloud dashboard remains online when the phone sleeps. **The current worker is a manually started session, not a verified unattended daily scheduler**; operator setup and the daily OAuth lifecycle must be completed before promising reliable unattended multi-day simulations.

The API uses [Upstox Full Market Quotes V3](https://upstox.com/developer/api-documentation/get-full-market-quote-v3/), [Intraday Candles V3](https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/), and the [daily JSON instrument master](https://upstox.com/developer/api-documentation/instruments/). For fees see [Upstox Basic pricing](https://upstox.com/brokerage-charges/) and [Zerodha charges](https://zerodha.com/charges/). No brokerage account is needed for the synthetic demo; actual Upstox access depends on account/API eligibility and may have its own charges or platform restrictions.

### Commands at a glance

```bash
python tools/india.py demo-generate
python tools/india.py dashboard --mode demo                   # phone/local demo
python tools/india.py dashboard --mode upstox                 # real data, read-only report
python tools/india.py upstox-sync                             # public instrument master
python tools/india.py paper-upstox --market NIFTY --lots 1    # live REST snapshots, paper only
python tools/india.py paper-upstox --market SENSEX --lots 1   # separate session; avoid concurrent workers
python tools/india.py paper-report --directory trader/paper_upstox --fixed-cost-per-month 0
python tools/india.py paper-cost --exchange NFO --buy 100 --sell 120 --qty 65 --fee-profile UPSTOX
```

## What works

| Codex skill | India workflow | Current implementation |
|---|---|---|
| `$trader-scanner` | 09:15–09:30 IST opening-range breakout on 5m candles | Offline CSV / Kite historical candles |
| `$trader-news` | Indian-market RSS headlines | Google News RSS, verify original |
| `$trader-entry` | Confirm first **closed** breakout candle | Offline CSV / Kite historical candles |
| `$trader-exit` | Stop and R-multiple target | Static order plan, no stop submitted |
| `$trader-timemachine` | Historical ORB outcomes + 10,000 sampled paths | Historical CSV only, simulation not prediction |
| `$trader-budget` | INR loss-based position sizing | Cash equity; options/futures require fresh master & contract-specific manual prices |
| `$trader-risk` | Limits, index gate, lot size, daily loss | Static checks; exchange/margin validation needed |
| `$trader-broker` | Paper ticket and paper journal | No live trade submission or fill simulation |
| `$trader-alerts` | On-demand quote threshold checks | Reads Kite LTP or explicit test LTP; not background notifications |
| `$trader-analyst` | Earnings comparison | User-supplied filing-derived CSV only |
| `$trader-pelosi` | Indian corporate-insider disclosure analog | User-supplied public disclosure CSV; original US Pelosi tracker available from upstream import |

### Crucial instrument separation

- `NSE:NIFTY 50` and `BSE:SENSEX` are **index data symbols**, not orders you can place for the indices.
- Use the indices to find a setup. For actual tradable options or futures, choose a *separate, current* `NFO:<contract>` or `BFO:<contract>` from Kite's instrument master. The index price **must never** be reused as the premium or stop of an option.
- **All derivatives are blocked by default** (`allow_derivatives: false`); changing this only enables *paper analysis and sizing*, not live execution. Actual instrument margin, contract expiry, dynamic strike selection, liquidity and exchange rules are not modeled.
- Indian equity shorts are blocked by default (`allow_short: false`); shorts can require MIS and exchange/broker eligibility.

## Installation (Windows + VS Code / Codex)

1. Download and extract this ZIP, keeping the top-level `.agents` folder (Windows Explorer may hide dot-prefixed folders).
2. Open the extracted `codex-india-day-trader` directory in **VS Code with Codex**, or from Codex CLI.
3. Ensure `py -3 --version` shows Python 3.9+.
4. From PowerShell in the project root, run:

   ```powershell
   py -3 -m unittest discover -s tests -v
   py -3 tools/india.py timemachine --csv examples/synthetic_25sessions.csv --iterations 10000
   ```

5. In Codex, use a skill by name, e.g. **`$trader-scanner`**: *"Analyze NIFTY 50 using the first 15-minute opening range, from verified Kite data. Do not place orders."*

This directory's `.agents/skills/trader-*/SKILL.md` files are already project-installed. To install all eleven **globally** for your user account instead, run from PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME/.agents/skills" | Out-Null
Copy-Item '.agents/skills/trader-*' "$HOME/.agents/skills/" -Recurse -Force
```

Restart Codex if you don't see them in the skill selector. Check `$trader-scanner` and `/skills`. **The Python tools stay in the project directory**, so keep that directory open when using these skills; global SKILL.md installation alone doesn't copy the execution engine.

For Linux/macOS: `python3 -m unittest discover -s tests -v` then `python3 tools/india.py ...`.

## Run without Zerodha (offline)

The example file **contains synthetic prices, NOT actual NIFTY/SENSEX data**. Do not use its performance numbers for trading decisions.

```bash
python tools/india.py scan --symbol "NSE:NIFTY 50" --date 2026-10-22 --csv examples/synthetic_25sessions.csv
python tools/india.py entry --symbol "NSE:NIFTY 50" --date 2026-10-22 --csv examples/synthetic_25sessions.csv --as-of "2026-10-22T09:35:00+05:30"
python tools/india.py exit --signal trader/signal.json --stop mid --rr 1.5
python tools/india.py timemachine --csv examples/synthetic_25sessions.csv --iterations 10000
```

**Note:** `scan` or `entry` writes `trader/signal.json`. The other steps consume and overwrite local state files; these are intentionally ignored by git.

CSV required columns: `date,open,high,low,close,volume`. Use timestamp ISO-8601 with `+05:30`, e.g. `2026-11-11T09:15:00+05:30`. If no timezone provided, the parser assumes IST. Use one row per **5-minute bar starting at the timestamp**. Use verifiable real historical bars for any actual conclusions.

## Zerodha Kite Connect setup (read-only)

1. Create a Kite Connect app via https://developers.kite.trade/ and follow Zerodha's [Kite login flow](https://kite.trade/docs/connect/v3/user/). The **Personal (free)** API does **not** provide historical or live market data. Kite Connect with data access is currently advertised at **₹500/month per app**; verify current pricing before purchase.
2. Register your redirect URL, obtain your API key and secret. Log in through Kite and exchange the short-lived `request_token` for an `access_token` using Zerodha's docs. **Do not paste the secret or token into Codex chat.**
3. In the same terminal session, set environment variables. For PowerShell (replace with values locally, never commit them):

   ```powershell
   $env:KITE_API_KEY = '<your-api-key>'
   $env:KITE_ACCESS_TOKEN = '<your-current-access-token>'
   ```

   On Linux/macOS: `export KITE_API_KEY='...'` and `export KITE_ACCESS_TOKEN='...'`.

4. Create local private config (Windows):

   ```powershell
   Copy-Item trader/config.example.json trader/config.json
   ```

   Or Unix: `cp trader/config.example.json trader/config.json`.

5. Edit only **local** `trader/config.json` to set your INR capital and risk limits.
6. Sync Kite instrument master and run a market-data scan:

   ```bash
   python tools/india.py instruments sync
   python tools/india.py instruments resolve --symbol "NSE:NIFTY 50"
   python tools/india.py instruments resolve --symbol "BSE:SENSEX"
   python tools/india.py scan --symbol "NSE:NIFTY 50" --date 2026-11-11
   python tools/india.py scan --symbol "BSE:SENSEX" --date 2026-11-11
   python tools/india.py export-history --symbol "NSE:NIFTY 50" --from-date 2026-09-01 --to-date 2026-11-11 --out trader/nifty_history.csv
   python tools/india.py timemachine --csv trader/nifty_history.csv --iterations 10000
   ```

   Use a real trading day on which your plan has historical data. Index symbol names must match the daily instrument master; `instruments resolve` checks this explicitly. Download the master each trading day (once, rather than per ticker), especially before trading derivatives.

`export-history` splits 5-minute historical retrieval into approximately 50-day windows and writes a timestamped CSV. Use a valid current instrument token, and consider Kite's data retention limits and rate limits. Check actual returned bar count, timezone, missing sessions and market holidays before interpreting results.

**Sessions expire:** Zerodha's access token normally expires at **06:00 IST the following day**. Credentials require routine renewal using the official login flow. This package deliberately does not attempt to bypass authentication or automate login.

**Connectivity note:** The package's Kite historical and instrument endpoints are implemented according to the official REST docs. They cannot be verified here against a live account without a user's key, subscription and network access. Rate limits, broker permissions and exchange closures can block live calls.

## Use a NIFTY/SENSEX signal with a paper trade

For cash equities with a verified signal on the **same** equity, the usual flow is:

```bash
python tools/india.py scan --symbol NSE:RELIANCE --date 2026-11-11
python tools/india.py exit --stop mid --rr 1.5
python tools/india.py budget --symbol NSE:RELIANCE
python tools/india.py risk --daily-pnl 0 --trades-today 0
python tools/india.py broker ticket
python tools/india.py broker paper
```

For a **NIFTY or SENSEX index signal**, never call `budget` with the index plan directly. Instead, open Zerodha and find the exact current tradable NFO/BFO contract, inspect **that contract's own market price, stop and target**, then make an independent plan:

```bash
# EXAMPLE ONLY. Replace all fictional numbers with the real instrument, verified premium and risk plan.
python tools/india.py manual-plan --symbol 'NFO:YOUR_CURRENT_CONTRACT' --side BUY --entry 100 --stop 90 --target 120
# Deliberately fails until config explicitly permits derivatives and instrument master contains the contract.
python tools/india.py budget --symbol 'NFO:YOUR_CURRENT_CONTRACT'
python tools/india.py risk
python tools/india.py broker ticket
```

A successful `risk` check is only an internal check. It does **not** validate margin availability, liquidity, freeze quantities, exchange holidays, transaction costs, option Greeks, limit order fills, current tick sizes, broker rejection risk, or hedged multi-leg execution.

**No live orders.** `python tools/india.py broker live` always blocks. `broker paper` requires a matching `trader/risk.json` PASS for that exact ticket, then creates only a journal entry with status `PAPER_RECORDED_NOT_FILLED`: it does not simulate price execution or submit stop-loss/take-profit orders. Stops, targets, and time exits are analytic plans, not broker-protected orders.

## Other workflows

```bash
python tools/india.py news --query 'NIFTY 50 market India'
python tools/india.py alerts add --symbol NSE:RELIANCE --above 2700
python tools/india.py alerts check --symbol NSE:RELIANCE --ltp 2720
python tools/india.py analyst --csv examples/quarterly_template.csv
python tools/india.py insiders --csv examples/insider_template.csv
```

`alerts check` is **on demand**. It doesn't send push notifications, run a daemon or guarantee the alert fires at the crossing time. `--ltp` is a user-supplied price for offline testing; omit it to request a Kite LTP snapshot with credentials. Filings and disclosure examples are **fictional template data**. Public RSS headlines may be incomplete and should be verified with the exchange/company.

## Import original upstream files (optional)

The project itself contains 11 Codex skill definitions plus the India engine. If you also want **all original upstream Python scripts and Claude SKILL.md files**, download that repository on your local computer, then import its eleven folders unchanged into `vendor/upstream/`:

```bash
git clone https://github.com/Jakeschincariol/day-trader-skill.git
python scripts/import_upstream.py --source day-trader-skill
```

The upstream US scripts are **preserved for reference/compatibility**, not automatically integrated into Indian workflows. They use original paths and may require their own broker access. Do not run the original `/trader-broker` for real orders without separately reviewing its implementation, credentials and safeguards. The original project is MIT licensed; check its license in the cloned source.

## Test suite

Run: `python -m unittest discover -s tests -v`

Tests verify: 5-minute close confirmation/no lookahead, missing-range-bar checks, stop/target arithmetic, risk sizing, index-order rejection, derivatives and lot-size safeguards, conservative backtesting, CSV filing analysis, hard-blocked live orders and duplicate paper order prevention.

Not tested: Zerodha-authenticated historical data, paid market-data entitlements, BFO/NFO contract dynamics, exchange holiday calendars, live broker orders (none supported), continuous trade monitoring, Google News RSS connectivity. No Kite sandbox is offered; do not assume offline tests prove live connectivity.

## Strategy limitations

- This uses a **15-minute opening range** (09:15–09:30 IST) with **5-minute confirming closes**, an entry cutoff at 14:45 IST, and an intended flat-by time of 15:20 IST. That is one particular ORB strategy, not a validated profitable edge.
- Replaying 10,000 resampled returns is exploratory, not a probability forecast. Historical targets/stops are marked conservatively as **stop first** when both appear in the same bar.
- Real trades incur spreads, exchange fees, brokerage, transaction charges, STT, taxes, slippage and potential stop gaps; these are not modeled.
- Special sessions such as Muhurat trading, halts and NSE/BSE holidays are not determined automatically. Avoid using ordinary session logic on these dates.
- Existing `trader/` files are overwritten by some commands; keep backups of experimental analyses if needed.

## Sources

- Codex skill folders: https://learn.chatgpt.com/docs/build-skills
- Kite instrument lookup: https://kite.trade/docs/connect/v3/market-quotes/
- Kite historical candles: https://kite.trade/docs/connect/v3/historical/
- Kite authentication: https://kite.trade/docs/connect/v3/user/
- Zerodha pricing: https://zerodha.com/products/api
- Upstream 11-skill design: https://github.com/Jakeschincariol/day-trader-skill

---

## NEW: realistic quote-based forward PAPER trading (cost-aware)

**This mode does not submit any order to Zerodha. It observes actual quotes once your Kite account is connected and writes estimated virtual fills.** Read-only live Kite integration and actual network order-book feed have **not** been verified with a Zerodha account in this environment. Fee schedules were checked on 11 Nov 2026; verify them regularly at [Zerodha charges](https://zerodha.com/charges/).

### What it realistically includes

- Buy at the displayed **ask**, sell at displayed **bid** (not LTP or index close); walk the up-to-5 levels of available market depth and reject fills when too little is visible.
- Configurable **adverse slippage** and **latency**, stale quote checks, spread ceiling, option-points stop/target, and gap-through-stop execution at the later observed executable bid.
- **Intraday buy-to-open, sell-to-close** NFO/NIFTY and BFO/SENSEX option contracts only. Use a real unexpired daily Kite instrument (not the index), correct lot size and expiry; one one-way position per session.
- Zerodha estimated costs: ₹20 per executed options order; 0.15% sell-side STT on premium (effective 1 Apr 2026); exchange NFO 0.03553% or BFO SENSEX/BANKEX 0.0325% on premium turnover; SEBI ₹10/crore; GST 18% on brokerage + exchange fees + SEBI; stamp duty 0.003% of buy-side premium. The engine rounds each charge for display and STT to nearest rupee. **This is an estimate, not an exact contract note.**
- Journal: entry/exit triggers, rejected fills, simulated fills, gross P&L, fee breakdown, *net* realized P&L and estimated fee-adjusted break-even exit. Daily run caps against configured paper daily losses and max trades.
- Summary: win rate, net P&L, costs, per-trade expectancy, profit factor, closed-trade drawdown, and optional monthly fixed Kite-data expense allocation.

### 1. Demonstrate mechanics WITHOUT internet

The bundled quote file is **SYNTHETIC DATA FOR TESTING SOFTWARE ONLY**, not market evidence.

```powershell
py -3 -m unittest discover -s tests -v
py -3 tools/india.py paper-cost --exchange NFO --buy 100 --sell 120 --qty 65
py -3 tools/india.py paper-replay --quotes-csv examples/SYNTHETIC_option_quotes.csv --contract NFO:TESTNIFTY2026CE --qty 20
```

For a real historical quote replay, collect genuine *time-stamped bid/ask depth* from the live feed and reformat as `timestamp,bid,ask,bid_qty,ask_qty,last`. Historical **index 5-minute candles alone cannot recreate the option premiums, spreads, liquidity or executable fills**. Do not use the synthetic example's gains to select a strategy.

### 2. Run live paper trading during the exchange session (09:15–15:20 IST)

Create private settings: `Copy-Item trader/config.example.json trader/config.json`, then set:

```json
{
  "paper": true,
  "allow_derivatives": true,
  "allow_live_orders": false
}
```

*Keep all other fields from `config.example.json`*, including `capital_inr`, `max_loss_per_trade_inr`, `max_daily_loss_inr`, `max_trades_per_day`, `max_allocation_fraction`, and `instrument_cache`. In PowerShell set the local environment variables `$env:KITE_API_KEY` and `$env:KITE_ACCESS_TOKEN`; never post credentials in Codex or commit them to GitHub. Refresh your Kite login token when required.

Synchronize instrument master **every market morning**:

```powershell
py -3 tools/india.py instruments sync
py -3 tools/india.py instruments resolve --symbol "NSE:NIFTY 50"
py -3 tools/india.py instruments resolve --symbol "BSE:SENSEX"
```

Open the synced `trader/instruments.csv`, filter `exchange=NFO` for NIFTY or `exchange=BFO` for SENSEX, `instrument_type=CE` or `PE`, choose a **valid actual future expiry**, positive lot size and liquid strike, and copy the exact `EXCHANGE:TRADINGSYMBOL`. There is **no automatic ATM strike selection**, and the tool won't invent an option symbol.

**Run the closed-bar NIFTY ORB strategy** (09:15–09:30 opening range, 5-minute closing confirmation; signal BUY → manually selected CE, SELL → manually selected PE):

```powershell
py -3 tools/india.py paper-live --index "NSE:NIFTY 50" --contract "NFO:REPLACE_WITH_REAL_CE_OR_PE" --lots 1 --stop-pct 15 --target-pct 30 --slippage-bps 5 --latency-ms 750 --poll-seconds 3
```

**Run SENSEX ORB** (BFO contract):

```powershell
py -3 tools/india.py paper-live --index "BSE:SENSEX" --contract "BFO:REPLACE_WITH_REAL_CE_OR_PE" --lots 1 --stop-pct 15 --target-pct 30
```

This sample's 15% stop / 30% target, 5 bps slippage and 750 ms latency are **illustrative assumptions, not optimized parameters or measured real fills**. Adjust only after testing. If you start too late after the ORB trigger, the entry is skipped instead of creating a fictitious fill. Contracts mismatching the signal direction are skipped.

For **manual PAPER immediately** after opening the process, omit `--index`:

```powershell
py -3 tools/india.py paper-live --contract "NFO:REPLACE_WITH_REAL_OPTION" --lots 1
```

The script must keep running on an always-on PC/cloud host during the session. It writes append-only JSONL in `trader/paper_forward/`. Each run permits **at most one round-trip**, and paper positions remain unresolved if you stop the process while in a trade. A paper-only open position does not imply any real brokerage holding. The simulator checks stale quotes; missing depth, wide spreads, insufficient visible depth or insufficient estimated risk budget block fills.

**Limitation of polling:** Quotes arrive every few seconds, not every exchange tick. Your simulated outcome can materially differ from actual execution, especially in fast-moving/illiquid options. For better precision, upgrade from polling to Zerodha's **WebSocket** full-depth stream, record every timestamped packet to disk, and reconcile measured paper vs small controlled actual fills later *only if you independently choose to do so*. No account can guarantee future profit.

### 3. Aggregate your results after 20–30+ sessions

```powershell
py -3 tools/india.py paper-report --directory trader/paper_forward --fixed-cost-per-month 500 --assumed-trading-days 21
```

Report **net after fees and estimated data cost**, not just gross winning trades. For a credible strategy comparison, preserve *all* signals including skipped/rejected entries, test at least several market regimes, count losing days and max drawdown, and avoid parameter tuning on the same test window. The report only covers closed paper trades, and its fixed-cost allocation only counts days with closed trades; it is **not** a full monthly cashflow statement. Expiry/exercise STT, auto-squareoff fees, funding/margin, exchange penalties, taxes on income and missed executions are not included.

**Important:** The script does not simulate option selling-to-open, multi-leg strategies, futures, tick-level backtests or broker-confirmed executions. It makes no claims of guaranteed results. Live order placement is entirely absent.

### 4. Better contract selection: deterministic ATM mode

For an unbiased **first-signal, nearest non-expiring expiry, nearest-strike ATM** choice (BUY breakout → CE, SELL breakdown → PE), you can now omit the manually selected option contract:

```powershell
py -3 tools/india.py paper-live --index "NSE:NIFTY 50" --auto-atm --lots 1 --stop-pct 15 --target-pct 30
py -3 tools/india.py paper-live --index "BSE:SENSEX" --auto-atm --lots 1 --stop-pct 15 --target-pct 30
```

This avoids choosing only contracts that later performed well. At the first **new closed-bar ORB** signal, it selects a contract from the **current** Kite instrument master using the index's closed candle price and earliest **future** expiry (it deliberately excludes expiring-today contracts). Liquidity and fresh quote depth are still required; selection is not a guarantee of order acceptance or favorable prices. This is a consistent *candidate selection rule*, not a profitability-optimized strategy.

### 5. Audit every live quote instead of trusting the simulator

Each live paper journal now stores an append-only `QUOTE_SNAPSHOT` for every polled Kite response with timestamp, capture time, last, bid, ask and up-to-five depth levels. This permits an audit trail. Export top-of-book quotes for offline replay:

```powershell
py -3 tools/india.py paper-export-quotes --journal trader/paper_forward/YOUR_SESSION.jsonl --out trader/recorded_quotes.csv
py -3 tools/india.py paper-replay --quotes-csv trader/recorded_quotes.csv --contract NFO:YOUR_RECORDED_CONTRACT --qty YOUR_RECORDED_QUANTITY
```

The replay command assumes its entry signal at the first available quote (or at `--signal-time`), so **it does not necessarily reproduce an ORB-triggered live session** unless the proper signal time is supplied. It also uses top-of-book only; recorded full-depth and exact signal events remain in the JSONL journal for auditing. Observing quotes every 3 seconds can miss intervening order-book changes. Thus both figures are *estimates*—never broker-confirmed profits.
