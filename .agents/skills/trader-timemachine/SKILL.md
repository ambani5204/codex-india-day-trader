---
name: trader-timemachine
description: Backtest NIFTY/SENSEX opening-range setups with real historical CSV and cautious bootstrap simulations.
---

# trader-timemachine: Indian markets (Codex)

Work from the root of the `codex-india-day-trader` project. This is an Indian-market adaptation of the [upstream 11-skill pack](https://github.com/Jakeschincariol/day-trader-skill). It can be invoked as `$trader-timemachine` in Codex.

## Run

```bash
python tools/india.py timemachine --csv examples/synthetic_25sessions.csv --iterations 10000
```

Historical sample must be explicitly sourced. Simulator reports empirical outcomes and resampled time-of-day returns; never call it a prediction or imply the sample CSV is real.

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

The *separate research workflow* now runs a strictly finite, chronological, **96-candidate** walk-forward sweep on actual Upstox historical index candles: breakout/false break/trap/EMA/mean reversion, price efficiency (sideways avoidance), EMA trend alignment, opening-range compression, breakout candle-body strength and alternative trend reward:risk targets. It models **transaction-cost stress only as a hypothetical index-FUTURES proxy** (brokerage, historically dated STT, GST, stamp duty, exchange/IPFT/SEBI charges), not executable futures or options P&L. The train/validation/final-holdout and 2-point slippage stress gate can legitimately return **NO_CANDIDATE_PASSED**. In particular, do not cherry-pick historical R to fabricate a profitable strategy, and NEVER auto-change live paper settings.

Run `bash research-index-year.sh` after `git pull` on Termux using the existing historic index cache. Or use `python tools/india.py research-index-walk-forward --from-date 2025-10-01 --to-date 2026-10-01 --market AUTO --max-configs 96 --slippage-points 1`. A separate [GitHub Actions nightly event](../../../.github/workflows/nightly-index-strategy-research.yml) is configured weekdays around 23:00 IST, but downloading missing real candles on GitHub requires the private `UPSTOX_ACCESS_TOKEN` repository Actions secret and may require renewal. Without it, the job reports NOT_RUN, not fabricated results. The advanced intraday options/hedged spread worker itself still **has not been validated on historical option-chain quotes**.

See [Indian 11-skill integration and limits](../../../docs/INDIA_11_SKILLS.md). The full-day strategy is explicitly opt-in with `PAPER_MODE=advanced bash live-paper-android.sh`; legacy ORB remains the default. No live broker orders. 
