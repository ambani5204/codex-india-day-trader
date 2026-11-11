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

read -r -p "Market [NIFTY/SENSEX] (default NIFTY): " market
market="${market:-NIFTY}"
market="${market^^}"
case "$market" in NIFTY|SENSEX) ;; *) echo "Choose NIFTY or SENSEX."; exit 1;; esac

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
python tools/india.py paper-upstox --market "$market" --lots 1 --fee-profile UPSTOX > trader/upstox_worker.log 2>&1 &
worker=$!
trap 'kill "$worker" 2>/dev/null || true' EXIT
sleep 2
if ! kill -0 "$worker" 2>/dev/null; then
  echo "Data session did not start. Recent log:"
  tail -n 12 trader/upstox_worker.log
  exit 1
fi
echo "Open Chrome: http://127.0.0.1:8080"
echo "Market: $market | Paper trades only | No real orders"
python tools/india.py dashboard --mode upstox --host 127.0.0.1 --port 8080
