#!/usr/bin/env bash
# Phone-only forward paper trading. No broker order placement.
set -euo pipefail
cd "$(dirname "$0")"

if ! python -c "import zoneinfo; zoneinfo.ZoneInfo('Asia/Kolkata')" 2>/dev/null; then
  echo "Installing India timezone data..."
  python -m pip install tzdata
fi

python - <<'PY'
import json
from pathlib import Path
src = Path('trader/config.json')
if not src.exists():
    src = Path('trader/config.example.json')
data = json.loads(src.read_text())
data['allow_derivatives'] = True
data['paper'] = True
data['allow_live_orders'] = False
Path('trader/config.json').write_text(json.dumps(data, indent=2) + '\n')
PY

read -r -p "Market [AUTO/BOTH/NIFTY/SENSEX] (default AUTO): " market
market="${market:-AUTO}"
market="${market^^}"
case "$market" in AUTO|BOTH|NIFTY|SENSEX) ;; *) echo "Choose AUTO, BOTH, NIFTY or SENSEX."; exit 1;; esac
if [ "$market" = "AUTO" ]; then
  market="$(python -c 'from datetime import datetime; from zoneinfo import ZoneInfo; from india_trader.schedule import market_for_day; print(market_for_day(datetime.now(ZoneInfo("Asia/Kolkata")).date()) or "")')"
  if [ -z "$market" ]; then echo "No weekday session today."; exit 1; fi
  echo "Today's scheduled market: $market"
fi

if ! python - <<'PY'
from datetime import datetime,time
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Asia/Kolkata"))
if not (now.weekday() < 5 and time(9, 15) <= now.time() < time(15, 10)):
    print("Start on a market weekday, between 09:15 and 15:10 IST.")
    raise SystemExit(1)
PY
then exit 1; fi

echo "Paste today's Upstox access token (input hidden)."
read -r -s -p "Token: " UPSTOX_ACCESS_TOKEN
echo
if [ -z "$UPSTOX_ACCESS_TOKEN" ]; then echo "Token is required."; exit 1; fi
export UPSTOX_ACCESS_TOKEN

echo "Syncing NIFTY and SENSEX option instruments..."
python tools/india.py upstox-sync

mkdir -p trader
workers=()
markets=("$market")
if [ "$market" = "BOTH" ]; then
  markets=("NIFTY" "SENSEX")
  export PAPER_MARKET_PARTITIONS=2
  echo "Virtual capital and loss limits will be split equally between both markets."
else
  export PAPER_MARKET_PARTITIONS=1
fi
cleanup() {
  for pid in "${workers[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
for item in "${markets[@]}"; do
  python tools/india.py paper-upstox --market "$item" --lots 1 --selector delta --delta-min 0.40 --delta-max 0.65 --target-delta 0.50 --fee-profile UPSTOX > "trader/upstox_${item,,}.log" 2>&1 &
  workers+=("$!")
done
sleep 2
for i in "${!workers[@]}"; do
  if ! kill -0 "${workers[$i]}" 2>/dev/null; then
    echo "Could not start ${markets[$i]} session. Check:"
    echo "trader/upstox_${markets[$i],,}.log"
    tail -n 12 "trader/upstox_${markets[$i],,}.log"
    exit 1
  fi
done
echo "Open Chrome: http://127.0.0.1:8080"
echo "Market: $market | Paper trades only | No real orders"
echo "Start once on each market day, ideally 9:15-9:30 IST. Keep Termux open."
python tools/india.py dashboard --mode upstox --host 127.0.0.1 --port 8080
