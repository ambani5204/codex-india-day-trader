#!/usr/bin/env bash
# Reusable PAPER-ONLY session runner for the morning/afternoon two-job split
# (CHG-20261127-1625). NEVER places real orders. Behaviour mirrors the former
# single-job inline step exactly when RUN_SIDECARS=1; the afternoon half sets
# RUN_SIDECARS=0 to run only the main CE/PE worker (sidecars are morning-only,
# one journal per day).
#
# Required env: FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET, FIREBASE_PROJECT_ID,
#   JOURNAL_REPO_TOKEN, UPSTOX_ACCESS_TOKEN, RUNNER_TEMP, GITHUB_STEP_SUMMARY.
# Split env (optional): PAPER_SESSION_END, PAPER_FLAT_BY (HHMM) honoured by the
#   worker + sidecars; RUN_SIDECARS (default 1).
set -uo pipefail
RUN_SIDECARS="${RUN_SIDECARS:-1}"

if [ -z "${FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET:-}" ]; then
  echo "::error::Firebase service account secret is missing; cannot publish dashboard"
  exit 1
fi
pip -q install google-auth requests
printf '%s' "$FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET" > "$RUNNER_TEMP/firebase-service-account.json"
chmod 600 "$RUNNER_TEMP/firebase-service-account.json"
export GOOGLE_APPLICATION_CREDENTIALS="$RUNNER_TEMP/firebase-service-account.json"
export PAPER_MARKET="BOTH"
export PAPER_STATE_FILE="$RUNNER_TEMP/paper-state"
export PAPER_STOP_FILE="$RUNNER_TEMP/paper-stop"
echo STARTING > "$PAPER_STATE_FILE"

# Durable private-only snapshots + live publishers run throughout the session.
python -m deploy.private_journal_checkpoint &
CHECKPOINT_PID=$!
PAPER_MARKET=NIFTY python -m deploy.firebase_live_publisher &
PUBLISHER_PID=$!
PAPER_MARKET=SENSEX python -m deploy.firebase_live_publisher &
SENSEX_PUBLISHER_PID=$!
PUBLISHER_STATUS=0
cleanup() {
  touch "$PAPER_STOP_FILE"
  wait "$PUBLISHER_PID" || PUBLISHER_STATUS=$?
  wait "$SENSEX_PUBLISHER_PID" || PUBLISHER_STATUS=$?
  kill "$CHECKPOINT_PID" 2>/dev/null || true
  wait "$CHECKPOINT_PID" 2>/dev/null || true
  rm -f "$GOOGLE_APPLICATION_CREDENTIALS"
  if [ "$PUBLISHER_STATUS" -ne 0 ]; then
    echo "::error::Firestore publisher exited with code $PUBLISHER_STATUS"
  fi
}
trap cleanup EXIT
echo RUNNING > "$PAPER_STATE_FILE"
python tools/india.py upstox-sync || echo "::warning::EMA9 instrument refresh failed"
export PAPER_SESSION_START_IST="$(TZ=Asia/Kolkata date +%H%M)"

EMA9_STATUS=0
THREE_STATUS=0
EMA_STATUS=0
THREE_PUBLISHER_PID=""
EMA_PUBLISHER_PID=""
if [ "$RUN_SIDECARS" = "1" ]; then
  # Isolated paper-only sidecars (separate journals + Firestore collections).
  python -m india_trader.ema9_v2_live_sidecar &
  EMA9_PID=$!
  python -m deploy.three_candle_live_publisher &
  THREE_PUBLISHER_PID=$!
  python -m deploy.ema9_ema15_live_publisher &
  EMA_PUBLISHER_PID=$!
  python -m india_trader.three_candle_live_sidecar &
  THREE_PID=$!
  python -m india_trader.ema9_ema15_live_sidecar &
  EMA_PID=$!
fi

set +e
python -m deploy.cloud_paper_session --market BOTH
result=$?
set -e
if [ "$result" -ne 0 ]; then echo FAILED > "$PAPER_STATE_FILE"; fi

if [ "$RUN_SIDECARS" = "1" ]; then
  wait "$EMA9_PID" || EMA9_STATUS=$?
  if [ -f "trader/ema9_v2_live/$(TZ=Asia/Kolkata date +%F).jsonl" ]; then
    python -m deploy.publish_ema9_v2_paper || EMA9_STATUS=$?
  fi
  wait "$THREE_PID" || THREE_STATUS=$?
  wait "$EMA_PID" || EMA_STATUS=$?
  if [ -s "trader/three_candle_live/$(TZ=Asia/Kolkata date +%F).jsonl" ]; then
    python -m deploy.publish_three_candle_paper || THREE_STATUS=$?
  else
    echo "::warning::3 Candle journal missing; publisher skipped (sidecar exit=$THREE_STATUS)"
    if [ "$THREE_STATUS" -eq 0 ] && [ "$PAPER_SESSION_START_IST" -lt 1445 ]; then THREE_STATUS=2; fi
  fi
  if [ -s "trader/ema9_ema15_live/$(TZ=Asia/Kolkata date +%F).jsonl" ]; then
    python -m deploy.publish_ema9_ema15_paper || EMA_STATUS=$?
  else
    echo "::warning::EMA9/15 journal missing; publisher skipped (sidecar exit=$EMA_STATUS)"
    if [ "$EMA_STATUS" -eq 0 ] && [ "$PAPER_SESSION_START_IST" -lt 1445 ]; then EMA_STATUS=2; fi
  fi
  kill "$THREE_PUBLISHER_PID" "$EMA_PUBLISHER_PID" 2>/dev/null || true
  wait "$THREE_PUBLISHER_PID" 2>/dev/null || true
  wait "$EMA_PUBLISHER_PID" 2>/dev/null || true
fi

{
  echo "### Strategy worker outcomes (sidecars=$RUN_SIDECARS)"
  echo "| Worker | Exit code |"
  echo "|---|---:|"
  echo "| Legacy CE/PE | $result |"
  echo "| EMA9 V2 | $EMA9_STATUS |"
  echo "| 3 Candle | $THREE_STATUS |"
  echo "| EMA9/15 | $EMA_STATUS |"
} >> "$GITHUB_STEP_SUMMARY"
if [ -f trader/cloud_paper_summary.json ]; then
  python -c 'import json; r=json.load(open("trader/cloud_paper_summary.json")); print("::notice::Legacy session status="+str(r.get("status"))+" startup="+str(r.get("startup"))+" detail="+str(r.get("failure_detail")))'
fi
if [ "$THREE_STATUS" -ne 0 ] || [ "$EMA_STATUS" -ne 0 ] || [ "$result" -ne 0 ]; then
  echo FAILED > "$PAPER_STATE_FILE"
else
  echo FINISHED > "$PAPER_STATE_FILE"
fi
cleanup
trap - EXIT
if [ "$THREE_STATUS" -ne 0 ] || [ "$EMA_STATUS" -ne 0 ]; then
  echo "::error::Strategy paper sidecar failed: 3 Candle=$THREE_STATUS EMA9/15=$EMA_STATUS"
  exit 1
fi
if [ "$EMA9_STATUS" -ne 0 ]; then echo "::warning::EMA9 V2 sidecar failed ($EMA9_STATUS)"; fi
if [ "$PUBLISHER_STATUS" -ne 0 ]; then exit "$PUBLISHER_STATUS"; fi
exit "$result"
