#!/usr/bin/env bash
# Four simple independent chart-trading hypotheses, no auto-deployment.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
TOKEN_FILE="$HOME/.config/codex-india-day-trader/upstox_analytics_token"
if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" && -s "$TOKEN_FILE" ]]; then
  IFS= read -r UPSTOX_ACCESS_TOKEN < "$TOKEN_FILE"
  export UPSTOX_ACCESS_TOKEN
fi
echo "Simple ORB/EMA research only; one hypothetical index trade/day, no option calls."
echo "Uses cached index data and conservative fee/slippage proxy."
echo "NEVER automatically scales lots or deploys changes to the paper trading engine."
python tools/india.py research-simple-edge \
  --from-date 2025-10-01 \
  --to-date 2026-10-01 \
  --market "${SIMPLE_MARKET:-AUTO}" \
  --slippage-points "${SIMPLE_SLIPPAGE_POINTS:-1}" \
  --out trader/backtests/simple_edge_2025-10-01_to_2026-10-01.json
