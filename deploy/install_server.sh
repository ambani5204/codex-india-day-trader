#!/usr/bin/env bash
# Run once on an Ubuntu/Debian Linux VPS (NOT in Android Termux).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ] || ! command -v systemctl >/dev/null; then
  echo "Requires Linux with python3 and systemd"; exit 1
fi
if ! "$PYTHON" -c 'from zoneinfo import ZoneInfo; ZoneInfo("Asia/Kolkata")' >/dev/null 2>&1; then
  echo "Missing timezone database. Run: sudo apt install tzdata"; exit 1
fi
umask 077
ENV_FILE="$ROOT/.env.paper"
if [ ! -f "$ENV_FILE" ]; then
  read -r -s -p "Paste your NEW Upstox Analytics Token (hidden): " TOKEN
  echo
  if [[ ! "$TOKEN" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "Unexpected token format. Nothing saved."; exit 1
  fi
  printf 'UPSTOX_ACCESS_TOKEN=%s\n' "$TOKEN" > "$ENV_FILE"
  unset TOKEN
  chmod 600 "$ENV_FILE"
else
  echo "Existing private token file retained: $ENV_FILE"
fi
mkdir -p "$HOME/.config/systemd/user"
RUNNER_UNIT="$HOME/.config/systemd/user/codex-paper-runner.service"
DASH_UNIT="$HOME/.config/systemd/user/codex-paper-dashboard.service"
cat > "$RUNNER_UNIT" <<EOF
[Unit]
Description=Codex India read-only Upstox paper scheduler
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON $ROOT/deploy/cloud_runner.py
Restart=always
RestartSec=20
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
cat > "$DASH_UNIT" <<EOF
[Unit]
Description=Codex India paper trading dashboard (localhost only)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON $ROOT/tools/india.py dashboard --mode upstox --host 127.0.0.1 --port 8080
Restart=always
RestartSec=10
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now codex-paper-runner.service codex-paper-dashboard.service
echo
echo "Installed: daily automatic paper runner + always-on local dashboard."
echo "Inspect: systemctl --user status codex-paper-runner"
echo "Daily report: python3 tools/india.py db-report --period day"
echo "Monthly report: python3 tools/india.py db-report --period month"
echo
echo "IMPORTANT: To survive SSH logout and server restart run:"
echo "sudo loginctl enable-linger $USER"
echo
echo "Dashboard listens only on 127.0.0.1:8080."
echo "For private Android HTTPS access, set up Tailscale and run: tailscale serve --bg 8080"
