---
name: trader-scanner
description: NSE/BSE chart scanning and 15-minute opening-range breakout detection for NIFTY, SENSEX or Indian equities.
---

# trader-scanner: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-scanner` in Codex.

## Run

```bash
python tools/india.py scan --symbol "NSE:NIFTY 50" --date 2026-11-11
```

Fetch closed five-minute candles from Kite Historical API; compute an opening range from 09:15–09:30 IST and first closed breakout after 09:30. Use --csv for reproducible offline data. Run only with a Kite session or CSV, never invent candles.

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

## Upstox 5-minute ORB feed (paper only)

If the user has a valid Upstox OAuth token, the non-Kite path is `python tools/india.py upstox-sync` followed by `python tools/india.py paper-upstox --market NIFTY` or `--market SENSEX`. It processes the first fully **closed** 5-minute candle beyond the 09:15–09:30 opening range, then uses an actual ATM option instrument from today's exchange master for paper execution. No live orders. Avoid claiming websocket tick-speed: the current connector polls Upstox V3 REST snapshots. For no account: `python tools/india.py demo-generate` and `python tools/india.py dashboard --mode demo` always produces **SYNTHETIC** demonstration prices, not actual NIFTY/SENSEX data.

## Full-day India options skill relationship

Experimental all-day scanning of completed Upstox 5-minute NIFTY/SENSEX candles adds ORB, EMA cross, and mean reversion. No lookahead; no guaranteed signals.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
