#!/usr/bin/env bash
# Exact index SIGNAL rules from the full-day simulator, 1 Oct 2025–1 Oct 2026.
# This cannot calculate realistic options CE/PE / credit spread P&L from index candles.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
TOKEN_FILE="$HOME/.config/codex-india-day-trader/upstox_analytics_token"
if [ ! -s "$TOKEN_FILE" ]; then
  echo "No saved Upstox Analytics Token found."
  echo "Run bash live-paper-android.sh once to validate and save your private token."
  exit 1
fi
IFS= read -r UPSTOX_ACCESS_TOKEN < "$TOKEN_FILE"
export UPSTOX_ACCESS_TOKEN
if [ -z "$UPSTOX_ACCESS_TOKEN" ]; then echo "Saved token is empty"; exit 1; fi
echo "Replaying 01 Oct 2025 to 01 Oct 2026 using Upstox historical 5-minute candles."
echo "Trading schedule: Mon/Tue/Fri NIFTY; Wed/Thu SENSEX."
echo "Signal replay only — cannot reconstruct historical option quotes/delta from index candles."
python tools/india.py backtest-index-signals \
  --from-date 2025-10-01 \
  --to-date 2026-10-01 \
  --market AUTO \
  --out trader/backtests/index_signals_2025-10-01_to_2026-10-01.json
unset UPSTOX_ACCESS_TOKEN
