---
name: trader-risk
description: Apply account, exchange, contract lot-size, daily loss and position limits to proposed Zerodha paper tickets.
---

# trader-risk: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-risk` in Codex.

## Run

```bash
python tools/india.py risk --order trader/orders.json --daily-pnl 0 --trades-today 0
```

Reject index-symbol orders. Derivatives disabled by default. A PASS covers stated static checks only and not broker margin, fills, or exchange rules; verify current restrictions.

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

Experimental engine keeps original paper trade/day risk caps and rejects naked short options, invalid liquidity and unresolved prior sessions. Spread margin/settlement are not broker verified.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
