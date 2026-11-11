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

# The Analytics Token is retained ONLY inside Termux's private app directory.
# Never commit it, store it in shared Android storage, or print it to the terminal.
TOKEN_DIR="$HOME/.config/codex-india-day-trader"
TOKEN_FILE="$TOKEN_DIR/upstox_analytics_token"
mkdir -p "$TOKEN_DIR"
chmod 700 "$TOKEN_DIR"

read_new_token() {
  echo "Enter your private Upstox Analytics Token (hidden). Never paste it into chat."
  UPSTOX_ACCESS_TOKEN=""
  read -r -s -p "Analytics Token: " UPSTOX_ACCESS_TOKEN
  echo
  if [ -z "$UPSTOX_ACCESS_TOKEN" ]; then
    echo "Token required."; return 1
  fi
  export UPSTOX_ACCESS_TOKEN
}

validate_token() {
  # Exit code 3 is an explicitly rejected/expired token (HTTP 401).
  # Connectivity/API errors have a different exit code: keep the saved token.
  python - <<'PY'
import sys
from india_trader.upstox import UpstoxReader, INDICES
try:
    UpstoxReader().candles(INDICES['NIFTY'])
    print('Upstox market-data authentication: OK', flush=True)
except Exception as exc:
    message = str(exc)
    print('Upstox validation failed: '+message, flush=True)
    sys.exit(3 if 'HTTP 401' in message else 2)
PY
}

save_token() {
  local temporary
  temporary="$(mktemp "$TOKEN_DIR/.token.XXXXXXXX")"
  chmod 600 "$temporary"
  printf '%s\n' "$UPSTOX_ACCESS_TOKEN" > "$temporary"
  mv -f "$temporary" "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  echo "Token saved in private Termux storage. It will be reused next time."
}

token_from_file=0
needs_save=0
UPSTOX_ACCESS_TOKEN=""
if [ -f "$TOKEN_FILE" ]; then
  chmod 600 "$TOKEN_FILE"
  IFS= read -r UPSTOX_ACCESS_TOKEN < "$TOKEN_FILE" || true
  if [ -n "$UPSTOX_ACCESS_TOKEN" ]; then
    token_from_file=1
    export UPSTOX_ACCESS_TOKEN
    echo "Checking saved Upstox Analytics Token..."
  fi
fi
if [ "$token_from_file" -eq 0 ]; then
  read_new_token
  needs_save=1
fi

if validate_token; then
  :
else
  status=$?
  if [ "$status" -eq 3 ] && [ "$token_from_file" -eq 1 ]; then
    echo "Saved token expired or was revoked. Enter a replacement."
    read_new_token
    if ! validate_token; then
      echo "Replacement token failed verification; saved token unchanged."
      exit 1
    fi
    needs_save=1
  else
    echo "Market-data validation failed; saved token unchanged."
    exit 1
  fi
fi

if [ "$needs_save" -eq 1 ]; then
  save_token
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
