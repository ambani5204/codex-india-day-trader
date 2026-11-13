"""Nightly read-only strategy evaluation from verified Firestore paper history."""
import datetime as dt
import os
from collections import defaultdict
from india_trader.core import IST


def evaluate(rows, now=None):
    now = now or dt.datetime.now(IST)
    valid = [r for r in rows if r.get("data_type") == "PAPER_SIMULATION"
             and r.get("date_ist") and r.get("market") in ("NIFTY", "SENSEX")]
    valid.sort(key=lambda r: (r["date_ist"], r["market"]))
    trades = sum(int(r.get("closed_trades") or 0) for r in valid)
    covered = sum(int(r.get("pnl_coverage") or 0) for r in valid)
    net = [float(r["net_pnl"]) for r in valid if isinstance(r.get("net_pnl"), (int, float))
           and not isinstance(r.get("net_pnl"), bool)]
    wins = sum(int(r.get("winning_trades") or 0) for r in valid if r.get("winning_trades") is not None)
    losses = sum(int(r.get("losing_trades") or 0) for r in valid if r.get("losing_trades") is not None)
    by_market = defaultdict(lambda: {"sessions": 0, "closed_trades": 0, "net_pnl": 0.0, "pnl_sessions": 0})
    for row in valid:
        m = by_market[row["market"]]
        m["sessions"] += 1
        m["closed_trades"] += int(row.get("closed_trades") or 0)
        if isinstance(row.get("net_pnl"), (int, float)):
            m["net_pnl"] += float(row["net_pnl"])
            m["pnl_sessions"] += 1
    # Review the strategies actually executed, not hypothetical index-only setups.
    strategies = defaultdict(lambda: {"closed_trades": 0, "verified_trades": 0,
        "winning_trades": 0, "losing_trades": 0, "net_pnl": 0.0,
        "modeled_stop_coverage": 0, "stop_exceedances": 0})
    for row in valid:
        for strategy, values in (row.get("strategy_stats") or {}).items():
            key = row["market"] + ":" + strategy
            dest = strategies[key]
            for field in ("closed_trades", "verified_trades", "winning_trades",
                          "losing_trades", "modeled_stop_coverage", "stop_exceedances"):
                dest[field] += int(values.get(field) or 0)
            if isinstance(values.get("net_pnl"), (int, float)):
                dest["net_pnl"] += float(values["net_pnl"])
    strategy_report = {}
    for name, v in strategies.items():
        strategy_report[name] = {**v,
            "net_pnl": round(v["net_pnl"], 2) if v["verified_trades"] else None,
            "win_rate": round(100 * v["winning_trades"] /
                (v["winning_trades"] + v["losing_trades"]), 1)
                if v["winning_trades"] + v["losing_trades"] else None,
            "review_flag": "INSUFFICIENT_SAMPLE" if v["verified_trades"] < 30
                else "STOP_MODEL_REVIEW" if v["stop_exceedances"] else "MONITOR"}
    return {
        "report_date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "status": "INSUFFICIENT_DATA" if trades == 0 or covered != trades else "EVALUATED",
        "sessions": len(valid),
        "closed_trades": trades,
        "verified_pnl_trades": covered,
        "net_pnl": round(sum(net), 2) if net else None,
        "win_rate": round(100.0 * wins / (wins + losses), 1) if wins + losses else None,
        "signals": sum(int(r.get("signals_count") or 0) for r in valid),
        "risk_rejections": sum(int(r.get("rejected_count") or 0) for r in valid),
        "system_errors": sum(int(r.get("errors_count") or 0) for r in valid),
        "strategy_reviews": strategy_report,
        "markets": {k: {**v, "net_pnl": round(v["net_pnl"], 2) if v["pnl_sessions"] else None}
                    for k, v in by_market.items()},
        "change_verified": False,
        "change_status": "NO_CANDIDATE_BACKTEST",
        "before_net_pnl": None,
        "after_net_pnl": None,
        "evaluation_type": "HISTORICAL_PAPER_PERFORMANCE",
    }


def firestore_field(value):
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: firestore_field(v) for k, v in value.items()}}}
    raise TypeError(type(value))


def unpack(field):
    if "integerValue" in field:
        return int(field["integerValue"])
    if "doubleValue" in field:
        return float(field["doubleValue"])
    if "stringValue" in field:
        return field["stringValue"]
    if "booleanValue" in field:
        return field["booleanValue"]
    if "mapValue" in field:
        return {k: unpack(v) for k, v in field["mapValue"].get("fields", {}).items()}
    return None


def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(creds)
    base = "https://firestore.googleapis.com/v1/projects/" + os.environ["FIREBASE_PROJECT_ID"] + "/databases/(default)/documents/"
    rows = []
    token = ""
    while True:
        response = session.get(base + "paper_history", params={"pageSize": 100, **({"pageToken": token} if token else {})}, timeout=25)
        if response.status_code == 404:
            break
        response.raise_for_status()
        payload = response.json()
        rows.extend({k: unpack(v) for k, v in doc.get("fields", {}).items()} for doc in payload.get("documents", []))
        token = payload.get("nextPageToken", "")
        if not token:
            break
    report = evaluate(rows)
    for doc in ("latest", report["report_date"]):
        response = session.patch(base + "paper_evaluations/" + doc,
            json={"fields": {k: firestore_field(v) for k, v in report.items()}}, timeout=25)
        response.raise_for_status()
    print("NIGHTLY_EVALUATION_PUBLISHED date=" + report["report_date"] +
          " status=" + report["status"] + " sessions=" + str(report["sessions"]) +
          " verified_trades=" + str(report["verified_pnl_trades"]), flush=True)


if __name__ == "__main__":
    main()
