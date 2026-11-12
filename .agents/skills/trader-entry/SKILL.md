---
name: trader-entry
description: Bar-close-confirmed NIFTY/SENSEX entry timing for the 09:15–09:30 opening range.
---

# trader-entry: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-entry` in Codex.

## Run

```bash
python tools/india.py entry --symbol "BSE:SENSEX" --date 2026-11-11
```

Wait for candle close. 09:30–09:35 is the first eligible 5m entry candle. An index breakout is analytical signal only, never a broker ticket. Use --as-of for point-in-time evaluation.

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

## Full-day India options skill relationship

On `PAPER_MODE=advanced`, range signals are classified **before** tradable Upstox contracts are selected. Bullish direction seeks long **CE** or a **bull put credit spread** (sell OTM PE + buy farther OTM PE); bearish direction seeks long **PE** or a **bear call credit spread** (sell OTM CE + buy farther OTM CE). No naked selling.

When chain IV is below the configurable exploratory threshold (default 18%), only a long CE/PE is considered. Above the threshold, directional **BREAKOUT/TRAP/EMA** prefer a long option and then a hedged credit spread if the first structure fails. **FAKEOUT/MEAN_REVERSION** prefer a hedged credit spread then a long option. This is a strategy-priority heuristic, **not** a validated IV predictor and not a comparison of unrelated reward:risk ratios.

All selected candidates must clear *their own* fee-adjusted R:R, bid-ask/depth, actual expiry, lot-size, risk and delayed paper-fill gates. Long CE/PE skip today's expiry; credit spreads use same-expiry short and hedge and block NEW same-day-expiry entries after 13:45 IST. Missing quotes/Greeks or a network failure must **not** be converted to fictional paper fills. Both structures may be rejected.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
