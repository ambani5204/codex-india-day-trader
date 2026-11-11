# Always-on private paper trading (Linux server)

**This is a setup guide. Nothing is deployed automatically to your account.**
The phone can be switched off once you deploy to an always-on Linux VPS.
Market-data requests are read-only. **No real orders are possible.**

## One-time setup (Ubuntu/Debian VPS)

SSH into a freshly provisioned, continuously running Linux VPS.

```bash
sudo apt update
sudo apt install -y python3 git tzdata
git clone https://github.com/ambani5204/codex-india-day-trader.git
cd codex-india-day-trader
bash deploy/install_server.sh
sudo loginctl enable-linger "$USER"
```

The installer asks once for a **new** Upstox Analytics Token. Paste it **on your server terminal**, not in GitHub/chat. It is saved in `.env.paper` with private file permissions, is excluded from Git, and is only used for read-only market APIs. Revoke any previously exposed tokens.

The installer enables two background services for this Linux user:

* `codex-paper-runner`: keeps watching the Indian clock while the server runs; starts the selected market once each Mon–Fri at 09:15–09:30 IST. The weekday schedule is Mon/Tue NIFTY, Wed/Thu SENSEX, Friday NIFTY.
* `codex-paper-dashboard`: listens on **127.0.0.1:8080 only**, at all times. Its database is `trader/paper.sqlite3`.

The worker simulates **one candidate trade/session per day**, and quits on trade completion, rejected entry, missed signal, data error or the session cutoff. No trade is guaranteed. It does not backfill missed sessions after outages. **NSE/BSE holidays are not yet automatically identified**. The script will attempt a weekday, but cannot invent a trading-day quote if the market is closed.

View status:

```bash
systemctl --user status codex-paper-runner
systemctl --user status codex-paper-dashboard
journalctl --user -u codex-paper-runner -n 40 --no-pager
python3 tools/india.py db-sync
python3 tools/india.py db-report --period day
python3 tools/india.py db-report --period month
```

## Open the private dashboard from Android

Use **Tailscale**, a private device network, rather than publishing port 8080 to the internet.

1. Install Tailscale on your VPS and Android phone, signed in to the same account/tailnet. Follow https://tailscale.com/download/linux and install the official Android app.
2. On the VPS, after `tailscale up`, run:

```bash
tailscale serve --bg 8080
tailscale serve status
```

3. Open the **private HTTPS .ts.net URL** displayed by Tailscale on your Android phone. It works with the same Tailscale account while the server runs, even if Termux is closed. Do not use `tailscale funnel`; that makes it public.

Official explanation: https://tailscale.com/docs/reference/tailscale-cli/serve

## Your data

* `trader/paper_upstox/*.jsonl`: detailed quote and event journal, flushed during the day.
* `trader/paper.sqlite3`: durable database of sessions, important events and closed trades.
* The dashboard now shows **Today** and **This month** net P&L. Use `db-report` for detailed summaries.

Both are on the VPS disk, surviving service restart and a normal server reboot. Make **off-server backups** for protection against disk loss. No actual Upstox trade or brokerage contract note is created.

**Important:** Dashboard/worker are not verified with a live Upstox account yet. A one-year Analytics Token can still be revoked or expire; renew it before its expiry and restart the runner. The system will not silently switch to synthetic prices after an API failure.
