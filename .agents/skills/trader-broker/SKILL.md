---
name: trader-broker
description: Review and journal paper orders for Zerodha instruments; never submit live orders.
---

# trader-broker: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-broker` in Codex.

## Run

```bash
python tools/india.py broker ticket --order trader/orders.json
```

Live order submission is intentionally unavailable. To paper-record use broker paper after risk checks. Do not claim actual fills, auto stop placement, or unattended trading.

## Prerequisites

- Python 3.9+ with `zoneinfo` (3.9 or later); no third-party dependencies for core/offline tools.
- For live **read-only** market data, create `trader/config.json` by copying `trader/config.example.json`, then set `KITE_API_KEY` and `KITE_ACCESS_TOKEN` in your local environment; never paste secrets into chat.
- For offline analysis supply `--csv` where supported. Confirm date, source, candle interval, correct Asia/Kolkata timezone, and whether bars are fully closed.
- Price data and indices are not executable contracts. Check actual current market structure, expiries, lot sizes and market holidays before any trading decision.

## Hard safety rules

1. Never place live orders. This package has no live-order transport, even if `allow_live_orders` is set.
2. Keep paper trading default, no margin or derivatives by default; require explicit human review.
3. Do not fabricate quotes, historical bars, earnings, disclosures, fill confirmations, or availability.
4. NIFTY 50 and SENSEX are index signals, NOT exchange-tradable instruments. Any proposed index-linked order must use an explicitly chosen tradable contract.
5. Cite market data source and timestamp in analysis; outputs are educational, not guarantees.

## Related skills

The other ten folders in `.agents/skills/` cover scan → entry → exit → timemachine → budget → risk → broker, plus news, alerts and analyst. Indian insider disclosures are provided by `trader-pelosi` to preserve the 11-skill organization. Optional original US Claude/Python contents can be copied with `scripts/import_upstream.py`.

## Forward live paper simulation (new)

For net profitability including estimated 2026 Zerodha taxes and charges, use:

```bash
python tools/india.py paper-cost --exchange NFO --buy 100 --sell 120 --qty 65
python tools/india.py paper-replay --quotes-csv examples/SYNTHETIC_option_quotes.csv --contract NFO:TESTNIFTY2026CE --qty 20
python tools/india.py paper-live --index "NSE:NIFTY 50" --contract 'NFO:REAL_OPTION_FROM_KITE_MASTER' --lots 1
python tools/india.py paper-report
```

Check README: `NEW: realistic quote-based forward PAPER trading`. The sample prices and symbols are fake test fixtures. `paper-live` requires a current Kite master, read-only Kite quote permission, actual option contract, derivative-paper permission and intraday session time; never claim confirmed fills. Prefer option depth to LTP, stop gaps fill at executable quote after observed latency; chart underlying index does NOT price the option. Only fully closed 5-minute ORB candles can create entry signals. Every result must display fees, spread, slippage, synthetic/live origin and remaining limitations. No code for real order placement is present.

## Upstox paper + mobile update

The `india_trader/upstox.py` connector is **read-only**; it uses full quotes and intraday 5-minute candles. With verified current-day Upstox OAuth and instrument master:

```bash
python tools/india.py upstox-sync
python tools/india.py paper-upstox --market NIFTY --lots 1 --fee-profile UPSTOX
python tools/india.py dashboard --mode upstox
```

For an account-free *synthetic example*, run `python tools/india.py demo-generate` then `python tools/india.py dashboard --mode demo`. Never present invented demo net profit as strategy validation. `paper-upstox` uses option quote bid/ask depth, stops/targets on the option **premium** after a closed index ORB trigger, conservative stale quote rejection, costs and modeled slippage. An index is NOT a tradable contract. There is no broker order submission code. No credentials in chat. Upstox OAuth access tokens expire daily; read-only dashboard uptime does not imply live data uptime.

## Full-day India options skill relationship

The experimental all-day engine journals ONLY hypothetical Upstox buy-to-open longs or hedged two-leg credit spreads and their quote-based closes. NO order endpoint or actual fills.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
