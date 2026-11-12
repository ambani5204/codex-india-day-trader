---
name: trader-exit
description: Entry-based stop, target and flat-before-close planning for Indian intraday analysis.
---

# trader-exit: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-exit` in Codex.

## Run

```bash
python tools/india.py exit --signal trader/signal.json --stop mid --rr 1.5
```

Set a stop at the opening-range midpoint or opposite end, and a risk-multiple target. Stop losses are theoretical until separately placed; never imply a broker stop has been submitted.

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

The advanced strategy computes different **index invalidation** prices from completed candles. A genuine breakout uses the confirmed breakout candle's low/high or a retest of the opening-range boundary; fakeout uses the swept wick extreme plus a buffer; a failed-breakout trap uses the most extreme price of its short outside-close episode plus a buffer. EMA uses a 6-bar swing plus ATR buffer; mean reversion uses a 3-bar swing plus ATR buffer.

Targets: breakout and EMA use a hypothetical **2R index-price projection**, fakeout targets the **opening-range midpoint**, trap targets the **opposite opening-range boundary**, and mean reversion targets the preceding 20-bar average. These are *plans, not expected price moves*. Long option estimates use live delta to map index stop/target into indicative option bid and require **net R:R ≥ 1.5 after fees**. Hedged credits use separate four-leg fee models and require estimated target/stop **net R:R ≥ 0.25** and positive target profit; both the modeled credit stop AND expiry payoff loss must fit the trade risk budget. If the target is not favorable or risk is unaffordable, skip without tightening the structural stop.

The model uses non-guaranteed REST snapshot monitoring. A quote outage can produce unresolved entries/exits, and actual losses could be larger than the estimated trade budget. The legacy `exit` command remains independent of the advanced paper mode.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
