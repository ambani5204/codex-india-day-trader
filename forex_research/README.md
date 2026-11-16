# Isolated forex research (not live trading)
This branch adds an opt-in manual GitHub Actions research workflow. Existing Indian trading workflows are unchanged.
## How to run
Actions → **Isolated Forex Research (CSV)** → Run workflow → choose pair and provide a public direct HTTPS URL to a CSV with columns `timestamp,open,high,low,close` and UTC one-minute bars spanning at least 700 days. Download the JSON artifact when complete.
## Limitations
No historical dataset is bundled; workflow will fail rather than fabricate performance if input is unavailable. Current research models six **approximations**, not exact parity with every Indian-market strategy. Fixed spreads and slippage are assumed, but broker commissions, swaps, financing, Indian taxes, real NSE futures fills, margin and expiry costs are NOT included. These JSON outputs must not be used to assert net tradable profit or authorize orders. For true India-compliant results, acquire historical contract-specific NSE cross-currency futures candles, quotes, and dated fees, then implement a separate executable-futures model.
No live trading, credentials, or Firebase modifications.
