from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import time

from india_trader.core import IST

ROOT = Path(__file__).resolve().parents[1]
JOURNALS = ROOT / "trader" / "paper_upstox"


def snapshot(market: str, state: str, run_id: str) -> dict:
    today = dt.datetime.now(IST).date().isoformat()
    records = []
    for path in sorted(JOURNALS.glob(f"{today}_{market}_*.jsonl")):
        try:
            with path.open(encoding="utf-8") as source:
                for line in source:
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict):
                            records.append(event)
                    except ValueError:
                        pass
        except OSError:
            pass
    rejected = [e for e in records if e.get("event") in ("ENTRY_REJECTED", "SIGNAL_REJECTED", "STRUCTURE_REJECTED", "ENTRY_BLOCKED")]
    errors = [e for e in records if e.get("event") in ("MARKET_DATA_ERROR", "UNRESOLVED_POSITION")]
    fills = [e for e in records if e.get("event") in ("PAPER_BUY_FILLED", "PAPER_SPREAD_OPEN")]
    closed = [e for e in records if e.get("event") == "PAPER_TRADE_CLOSED"]
    signals = [e for e in records if e.get("event") == "INDEX_SIGNAL"]
    important = [e for e in records if e.get("event") in ("INDEX_SIGNAL", "ENTRY_REJECTED", "SIGNAL_REJECTED", "STRUCTURE_REJECTED", "ENTRY_BLOCKED", "MARKET_DATA_ERROR", "PAPER_BUY_FILLED", "PAPER_SPREAD_OPEN", "PAPER_TRADE_CLOSED", "UNRESOLVED_POSITION")]
    recent = []
    for e in important[-35:][::-1]:
        recent.append({
            "time": str(e.get("timestamp") or e.get("time") or "")[:35],
            "type": str(e.get("event") or "")[:50],
            "reason": str(e.get("reason") or e.get("message") or "")[:200],
            "strategy": str(e.get("strategy") or "")[:80],
        })
    return {
        "date_ist": today,
        "market": market,
        "session_status": state,
        "updated_at": dt.datetime.now(IST).isoformat(),
        "run_id": run_id,
        "signals_count": len(signals),
        "entry_event_count": len(fills),
        "closed_trades": len(closed),
        "rejected_count": len(rejected),
        "errors_count": len(errors),
        "events": recent,
        "data_type": "PAPER_SIMULATION",
    }


def publish(data: dict) -> None:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    project = os.environ["FIREBASE_PROJECT_ID"]
    url = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/paper_dashboard/latest"
    def field(value):
        if isinstance(value, bool):
            return {"booleanValue": value}
        if isinstance(value, int):
            return {"integerValue": str(value)}
        if isinstance(value, list):
            return {"arrayValue": {"values": [field(item) for item in value]}}
        if isinstance(value, dict):
            return {"mapValue": {"fields": {k: field(v) for k, v in value.items()}}}
        return {"stringValue": str(value)}
    response = session.patch(url, json={"fields": {k: field(v) for k, v in data.items()}}, timeout=25)
    response.raise_for_status()
    history_url = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/paper_history/{data['date_ist']}"
    history = {k: v for k, v in data.items() if k != "events"}
    result = session.patch(history_url, json={"fields": {k: field(v) for k, v in history.items()}}, timeout=25)
    result.raise_for_status()


def loop(market: str, state_file: str, stop_file: str) -> None:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    while True:
        state = Path(state_file).read_text().strip() if Path(state_file).exists() else "STARTING"
        if Path(stop_file).exists():
            state = "FINISHED" if state == "RUNNING" else state
        try:
            publish(snapshot(market, state, run_id))
            print("Private Firestore session snapshot updated", flush=True)
        except Exception as exc:
            print("Firestore update failed:", type(exc).__name__, str(exc)[:160], flush=True)
        if Path(stop_file).exists():
            break
        time.sleep(30)


if __name__ == "__main__":
    loop(os.environ["PAPER_MARKET"], os.environ["PAPER_STATE_FILE"], os.environ["PAPER_STOP_FILE"])
