# Codex instructions: India Trader

Read the relevant `.agents/skills/trader-*/SKILL.md` before a trading-related action.
Run commands from this repository's root only.
Maintain clean separation between analytical signals for indices and **tradable** NSE/BSE/NFO/BFO contracts.
Always ask for independent instrument-specific contract prices before sizing derivatives; never reuse underlying index values.
Never create live orders or claim real fills. Keep paper only.
Market data and broker access may be unavailable; do not fabricate current prices.
Do not reveal or store Kite API keys, secrets, access tokens or request tokens in source files, terminals shown to the user, logs or chat.
Include timestamp, market, interval, data source, strategy limitations, risk and trade validation status in analyses.
Never remove protective gates simply to make a test pass.
For realistic profitability checks use `paper-replay`, `paper-live` (read-only full quotes), `paper-cost`, and `paper-report`. Never report synthetic example results as evidence of an actual trading edge. Quote depth, spread, stale-data checks, fee changes, slippage and unfilled orders are essential; inspect the README section on forward paper simulations. Costs are estimates to be reconciled with a real broker contract note. Ignore all broker auth secrets in analysis and do not build automated live order execution.

## Upstox forward PAPER simulator and Android dashboard

For broker-free demos use `python tools/india.py demo-generate` and `python tools/india.py dashboard --mode demo` (synthetic invented data only). The REST Upstox reader is `india_trader/upstox.py`; it uses GET market-data endpoints only. For real forward PAPER sessions: `python tools/india.py upstox-sync`, then `python tools/india.py paper-upstox --market NIFTY` (or SENSEX) before the new signal. Paper dashboard: `python tools/india.py dashboard --mode upstox`.

NEVER place or suggest orders through the backend. Never claim current real quote or profitability until a real authorized Upstox account connection, closed-candle timestamp and bid/ask depth are verified. Do not treat the broker-free synthetic dashboard as live. Costs include provisional UPSTOX Basic or ZERODHA round-trip options fee profiles, not precise contract-note reconciliation. The snapshot REST adapter is not a true streaming WebSocket feed; note sampling and slippage uncertainties. Upstox daily OAuth access token renewal is not automated, and no multi-day unattended simulation has been validated. Current-day instrument master and validated tradable option keys are mandatory; index itself must never be priced as an option. Any unresolved paper position must remain unresolved in the ledger; no backfilled fictitious exits.
