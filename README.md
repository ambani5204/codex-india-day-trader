# Codex Day Trader — India edition (NIFTY / SENSEX / Upstox / Zerodha / Android)

**Status: 29 offline tests passed, including the mock Upstox forward-paper workflow. Synthetic Android dashboard is runnable without an account. Upstox/Zerodha live-read connectivity is implemented but NOT yet verified using real credentials or exchange quotes. Cloud deployment is provided as a self-hosted configuration, not deployed here. NO live order execution.**

This project adapts the 11 skill *roles* from [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for **OpenAI Codex** in `.agents/skills/`. It is not the original repo's code ported line-for-line. For the original upstream Claude skill files and Python scripts, see [Import original files](#import-original-upstream-files-optional).

It is intended for **educational analysis** and controlled manual/paper workflows, not guaranteed profitability. Historical tests have lookahead and selection-bias risk unless verified against accurate, timestamped, independently collected market data.

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
