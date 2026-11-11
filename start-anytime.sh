#!/usr/bin/env bash
# Android/Termux: run once at any hour; waits for the next eligible paper session.
# Wake lock is best-effort: Android battery restrictions can still terminate Termux.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p trader

if ! python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Kolkata')" >/dev/null 2>&1; then
  echo "Installing required India timezone data..."
  python -m pip install tzdata
fi

dashboard_pid=""
wake_lock=0
cleanup() {
  if [ -n "$dashboard_pid" ]; then kill "$dashboard_pid" 2>/dev/null || true; fi
  if [ "$wake_lock" = "1" ] && command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if command -v termux-wake-lock >/dev/null 2>&1; then
  if termux-wake-lock; then
    wake_lock=1
    echo "Android CPU wake lock enabled."
  else
    echo "Warning: could not enable wake lock. Keep Termux allowed in background."
  fi
else
  echo "Warning: wake-lock command unavailable; Android may suspend Termux."
fi

echo "Use a fresh, private Upstox Analytics Token. Never paste tokens into chat."
read -r -s -p "Upstox Analytics Token (hidden): " UPSTOX_ACCESS_TOKEN
echo
if [ -z "$UPSTOX_ACCESS_TOKEN" ]; then
  echo "Token required."; exit 1
fi
export UPSTOX_ACCESS_TOKEN

# Verify the token against an authenticated read-only endpoint before overnight waiting.
if ! python - <<'PY'
from india_trader.upstox import UpstoxReader, INDICES
try:
    UpstoxReader().candles(INDICES['NIFTY'])
    print('Upstox authenticated market-data check: OK',flush=True)
except Exception as exc:
    print('Upstox data check failed: '+str(exc),flush=True)
    raise SystemExit(1)
PY
then
  echo "Fix or replace the token before leaving the app running overnight."
  exit 1
fi

# Keep the existing Upstox dashboard if already running; do not start a second server.
if python - <<'PY'
import json,urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2) as response:
        data=json.load(response)
    assert data.get('mode')=='upstox'
except Exception:
    raise SystemExit(1)
PY
then
  echo "Upstox dashboard is already running."
else
  python tools/india.py dashboard --mode upstox --host 127.0.0.1 --port 8080 > trader/termux_dashboard.log 2>&1 &
  dashboard_pid="$!"
  sleep 2
  if ! kill -0 "$dashboard_pid" 2>/dev/null; then
    echo "Dashboard could not start; another app might be using port 8080:"
    tail -n 8 trader/termux_dashboard.log
    exit 1
  fi
fi

echo "Dashboard: http://127.0.0.1:8080"
echo "Running in paper mode. No broker orders."
echo "You can turn the screen off. Do not force-stop Termux or reboot the phone."
echo "Android Settings > Apps > Termux > Battery: choose Unrestricted."
echo "Stop scheduler with CTRL+C."

python -u deploy/termux_runner.py 2>&1 | tee -a trader/termux_scheduler.log
