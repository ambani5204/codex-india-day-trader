#!/usr/bin/env bash
# Finite 96-combination offline research. Reuses private Upstox analytics token
# only when missing historical candle cache chunks need downloading.
# No broker orders, no paper-worker configuration changes, no auto-deployment.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
TOKEN_FILE="$HOME/.config/codex-india-day-trader/upstox_analytics_token"
if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" && -s "$TOKEN_FILE" ]]; then
  IFS= read -r UPSTOX_ACCESS_TOKEN < "$TOKEN_FILE"
  export UPSTOX_ACCESS_TOKEN
fi
echo "Bounded research: range breakout, fakeout, trap, EMA, mean reversion"
echo "Chronological train / validation / untouched holdout; transaction-tax futures COST PROXY."
echo "Never auto-deploys the trial with the best historical score."
python tools/india.py research-index-walk-forward \
  --from-date 2025-10-01 \
  --to-date 2026-10-01 \
  --market AUTO \
  --max-configs "${RESEARCH_CONFIGS:-96}" \
  --slippage-points "${RESEARCH_SLIPPAGE_POINTS:-1}" \
  --out trader/backtests/research_2025-10-01_to_2026-10-01.json
