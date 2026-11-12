#!/usr/bin/env bash
# Index-only historical intraday diagnostic, without CE/PE, expired chains,
# option Greeks, live orders or imaginary tradable-index INR profits.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
TOKEN_FILE="$HOME/.config/codex-india-day-trader/upstox_analytics_token"
if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" && -s "$TOKEN_FILE" ]]; then
  IFS= read -r UPSTOX_ACCESS_TOKEN < "$TOKEN_FILE"
  export UPSTOX_ACCESS_TOKEN
fi
echo "Historical 5-minute index CHART-POINT backtest: 01 Oct 2025–01 Oct 2026."
echo "Reuses trader/backtest_cache first; missing chunks require a valid Upstox token."
echo "This does not use or simulate put/call or any executable index instrument."
echo "Index-point R multiples are not actual INR trading returns."
python tools/india.py backtest-index-intraday \
  --from-date 2025-10-01 \
  --to-date 2026-10-01 \
  --market AUTO \
  --slippage-points "${INDEX_SLIPPAGE_POINTS:-0}" \
  --out trader/backtests/index_intraday_2025-10-01_to_2026-10-01.json
unset UPSTOX_ACCESS_TOKEN 2>/dev/null || :
