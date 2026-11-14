"""Publish separate unfilled research signal tracks for monitoring.

Never writes paper_history or paper_dashboard: those contain actual simulated
execution records and must not be contaminated with unfilled intents.
"""
import json
import os
from pathlib import Path

def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    from deploy.nightly_strategy_evaluation import firestore_field
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(creds)
    data = json.loads(Path(os.environ["DAILY_TRACK_REPORT"]).read_text())
    project = os.environ["FIREBASE_PROJECT_ID"]
    base = (f"https://firestore.googleapis.com/v1/projects/{project}"
            "/databases/(default)/documents/paper_strategy_signals/")
    for market in ("NIFTY", "SENSEX"):
        rows = [r for r in data["intents"] if r["market"] == market]
        summary = {
            "date_ist": data["date_ist"], "market": market,
            "strategy": "EMA9_FIB_PIVOT_V2",
            "status": "SIGNALS_ONLY_NOT_TRADES",
            "buy_signals": sum(x["track"] == "OPTION_BUY" for x in rows),
            "sell_signals": sum(x["track"] == "OPTION_SELL" for x in rows),
            "intraday_signals": sum(x["track"] == "INDEX_INTRADAY" for x in rows),
            "net_pnl_inr": None,
            "requires_option_quotes": True,
            "source": "github_actions_daily_research",
        }
        doc = f"{data['date_ist']}_{market}_EMA9_FIB_V2"
        resp = session.patch(base + doc,
            json={"fields": {k: firestore_field(v) for k, v in summary.items()}},
            timeout=30)
        resp.raise_for_status()
        print("PUBLISHED", doc, len(rows))
if __name__ == "__main__":
    main()
