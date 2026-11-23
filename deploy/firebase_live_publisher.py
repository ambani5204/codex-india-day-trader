from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import time

from india_trader.core import IST

ROOT = Path(__file__).resolve().parents[1]
JOURNALS = ROOT / "trader" / "paper_upstox"


def _actionable_paper_signals(records: list[dict]) -> list[dict]:
    """Count only eligible CE/PE paper intents, never raw index candidates.

    This relies on the paper engine's already-validated ENTRY_SIGNAL and
    paired OPTION_SELECTION, or its risk-sized two-leg PAPER_SPREAD_OPEN.
    It is not independent evidence of an exchange fill or immutable lineage.
    Missing/malformed legacy attribution fails closed to zero signals.
    """
    selections = {}
    qualified = []
    seen = set()
    for event in records:
        kind = event.get("event")
        session = event.get("session")
        stamp = event.get("timestamp")
        if not isinstance(session, str) or not session:
            continue
        if kind == "OPTION_SELECTION":
            contract = event.get("contract")
            if isinstance(contract, dict) and isinstance(contract.get("symbol"), str):
                selections[(session, contract["symbol"])] = (contract, stamp)
        elif kind == "ENTRY_SIGNAL":
            symbol = event.get("symbol")
            if not isinstance(symbol, str) or not symbol or not isinstance(stamp, str) or not stamp:
                continue
            selected = selections.get((session, symbol))
            if not selected:
                continue
            contract, selected_at = selected
            plan = contract.get("risk_plan")
            if (contract.get("option_type") not in ("CE", "PE")
                    or not isinstance(contract.get("expiry"), str)
                    or not isinstance(plan, dict)
                    or not isinstance(plan.get("quantity"), int)
                    or isinstance(plan.get("quantity"), bool)
                    or plan["quantity"] <= 0
                    or not isinstance(plan.get("stop_bid"), (int, float))
                    or not isinstance(plan.get("target_bid"), (int, float))
                    or not isinstance(selected_at, str) or selected_at > stamp):
                continue
            key = (session, "LONG", symbol, event.get("event_id") or stamp)
            if key not in seen:
                seen.add(key)
                qualified.append(event)
        elif kind == "PAPER_SPREAD_OPEN":
            contract = event.get("contract")
            if not isinstance(contract, dict) or not isinstance(stamp, str) or not stamp:
                continue
            if (contract.get("option_type") not in ("CE", "PE")
                    or not isinstance(contract.get("expiry"), str)
                    or not isinstance(contract.get("short_key"), str)
                    or not isinstance(contract.get("long_key"), str)
                    or contract["short_key"] == contract["long_key"]
                    or not isinstance(contract.get("quantity"), int)
                    or isinstance(contract.get("quantity"), bool)
                    or contract["quantity"] <= 0
                    or not isinstance(contract.get("estimated_max_expiry_loss_after_fees"), (int, float))
                    or contract["estimated_max_expiry_loss_after_fees"] <= 0):
                continue
            key = (session, "CREDIT", contract["short_key"], contract["long_key"],
                   event.get("event_id") or stamp)
            if key not in seen:
                seen.add(key)
                qualified.append(event)
    return qualified


def _entry_count_with_integrity(fills: list[dict]) -> tuple[int | None, str]:
    """Unknown on duplicated or unidentifiable fills, never inflate entry KPIs.

    Legacy timestamp keys are provisional; only producer-issued IDs can provide
    cross-restart idempotency. This checks one journal snapshot, not Firestore.
    """
    if not fills:
        return 0, "NO_FILL_EVENTS"
    seen = set()
    provisional = False
    for event in fills:
        session = event.get("session")
        stamp = event.get("timestamp")
        if (not isinstance(session, str) or not session
                or not isinstance(stamp, str) or not stamp):
            return None, "MISSING_FILL_IDENTITY"
        kind = event.get("event")
        if kind == "PAPER_BUY_FILLED":
            symbol = event.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                return None, "MISSING_FILL_CONTRACT"
            instrument = (symbol,)
        elif kind == "PAPER_SPREAD_OPEN":
            contract = event.get("contract")
            if not isinstance(contract, dict):
                return None, "MISSING_FILL_CONTRACT"
            short_key, long_key = contract.get("short_key"), contract.get("long_key")
            if (not isinstance(short_key, str) or not short_key
                    or not isinstance(long_key, str) or not long_key
                    or short_key == long_key):
                return None, "MISSING_FILL_HEDGE"
            instrument = (short_key, long_key)
        else:
            return None, "UNKNOWN_FILL_EVENT"
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            provisional = True
            event_id = stamp
        key = (session, kind, instrument, event_id)
        if key in seen:
            return None, "DUPLICATE_FILL_IDENTITY"
        seen.add(key)
    return len(fills), "PROVISIONAL_LEGACY_TIMESTAMP_ID" if provisional else "EVENT_IDS_PRESENT"


def snapshot(market: str, state: str, run_id: str, day: str | None = None) -> dict:
    today = day or dt.datetime.now(IST).date().isoformat()
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
    entry_count, entry_integrity = _entry_count_with_integrity(fills)
    closed = [e for e in records if e.get("event") == "PAPER_TRADE_CLOSED"]
    index_candidates = [e for e in records if e.get("event") == "INDEX_SIGNAL"]
    actionable_signals = _actionable_paper_signals(records)
    important = [e for e in records if e.get("event") in ("ENTRY_SIGNAL", "ENTRY_REJECTED", "SIGNAL_REJECTED", "STRUCTURE_REJECTED", "ENTRY_BLOCKED", "MARKET_DATA_ERROR", "PAPER_BUY_FILLED", "PAPER_SPREAD_OPEN", "PAPER_TRADE_CLOSED", "UNRESOLVED_POSITION")]
    # Calculate financial metrics from verified CLOSED paper fills, never from signals.
    # Preserve unavailable values as null when no closed trade has a net P&L.
    closed_with_pnl = [e for e in closed if isinstance(e.get("net_pnl"), (int, float))
                       and not isinstance(e.get("net_pnl"), bool)]
    net_pnl = round(sum(float(e["net_pnl"]) for e in closed_with_pnl), 2) if closed_with_pnl else None
    gross_pnl = round(sum(float(e.get("gross_pnl", 0)) for e in closed_with_pnl), 2) if closed_with_pnl else None
    fees_total = round(sum(float((e.get("fees") or {}).get("total", 0)) for e in closed_with_pnl), 2) if closed_with_pnl else None
    winning_trades = sum(float(e["net_pnl"]) > 0 for e in closed_with_pnl)
    losing_trades = sum(float(e["net_pnl"]) < 0 for e in closed_with_pnl)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for e in sorted(closed_with_pnl, key=lambda item: str(item.get("timestamp", ""))):
        equity += float(e["net_pnl"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    trade_ledger = []
    for e in sorted(closed, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:30]:
        entry_time = str(e.get("buy_time") or "")
        symbol = str(e.get("symbol") or "")
        session_id = str(e.get("session") or "")
        prior = [x for x in records if str(x.get("session") or "") == session_id
                 and str(x.get("timestamp") or "") <= entry_time]
        entry_signals = [x for x in prior if x.get("event") == "ENTRY_SIGNAL"
                         and str(x.get("symbol") or "") == symbol]
        entry_signal = max(entry_signals, key=lambda x: str(x.get("timestamp") or ""), default={})
        signal_time = str(entry_signal.get("timestamp") or "")
        selections = [x for x in prior if x.get("event") == "OPTION_SELECTION"
                      and str((x.get("contract") or {}).get("symbol") or "") == symbol
                      and (not signal_time or str(x.get("timestamp") or "") <= signal_time)]
        selection = max(selections, key=lambda x: str(x.get("timestamp") or ""), default={})
        contract = selection.get("contract") or {}
        plan = contract.get("risk_plan") or {}
        index_plan = contract.get("index_stop_plan") or {}
        trade_ledger.append({
            "time": str(e.get("timestamp") or ""),
            "entry_time": str(e.get("buy_time") or ""),
            "symbol": str(e.get("symbol") or ""),
            "side": "BUY TO OPEN / SELL TO CLOSE" if e.get("buy_price") is not None else "UNKNOWN",
            "quantity": e.get("quantity"),
            "entry_price": e.get("buy_price"),
            "exit_price": e.get("sell_price"),
            "gross_pnl": e.get("gross_pnl"),
            "fees": (e.get("fees") or {}).get("total"),
            "net_pnl": e.get("net_pnl"),
            "exit_reason": str(e.get("reason") or ""),
            "entry_strategy": str(entry_signal.get("reason") or ""),
            "signal_time": signal_time,
            "entry_explanation_available": bool(entry_signal and selection),
            "index_spot_at_decision": index_plan.get("index_spot"),
            "index_stop_at_decision": index_plan.get("index_stop"),
            "index_target_at_decision": index_plan.get("index_target"),
            "risk_budget_inr": plan.get("risk_cap_inr"),
            "estimated_stop_loss_inr": plan.get("estimated_stop_loss_including_charges"),
            "planned_target_price": plan.get("target_bid"),
            "planned_stop_price": plan.get("stop_bid"),
            "planned_reward_risk": plan.get("net_reward_risk"),
            "option_delta": contract.get("delta"),
            "selection_basis": str(contract.get("selection") or ""),

        })
    # Aggregate closed trades by the entry strategy recorded at decision time.
    # Unknown attribution is explicit; never infer a strategy from a later signal.
    strategy_stats = {}
    for trade in trade_ledger:
        name = trade.get("entry_strategy") or "UNATTRIBUTED"
        stat = strategy_stats.setdefault(name, {"closed_trades": 0, "verified_trades": 0,
            "winning_trades": 0, "losing_trades": 0, "net_pnl": 0.0,
            "modeled_stop_total": 0.0, "modeled_stop_coverage": 0,
            "stop_exceedances": 0})
        stat["closed_trades"] += 1
        pnl = trade.get("net_pnl")
        if isinstance(pnl, (int, float)) and not isinstance(pnl, bool):
            stat["verified_trades"] += 1
            stat["net_pnl"] += float(pnl)
            stat["winning_trades"] += int(pnl > 0)
            stat["losing_trades"] += int(pnl < 0)
            modeled = trade.get("estimated_stop_loss_inr")
            if isinstance(modeled, (int, float)) and modeled > 0:
                stat["modeled_stop_coverage"] += 1
                stat["modeled_stop_total"] += float(modeled)
                stat["stop_exceedances"] += int(-float(pnl) > float(modeled))
    for stat in strategy_stats.values():
        stat["net_pnl"] = round(stat["net_pnl"], 2) if stat["verified_trades"] else None
        stat["modeled_stop_total"] = round(stat["modeled_stop_total"], 2)
    recent = []
    for e in important[-35:][::-1]:
        recent.append({
            "time": str(e.get("timestamp") or e.get("time") or "")[:35],
            "type": str(e.get("event") or "")[:50],
            "reason": str(e.get("reason") or e.get("message") or "")[:200],
            "strategy": str(e.get("strategy") or "")[:80],
            "side": str(e.get("side") or "")[:20],
            "symbol": str(e.get("symbol") or "")[:90],
        })
    return {
        "date_ist": today,
        "market": market,
        "session_status": state,
        "updated_at": dt.datetime.now(IST).isoformat(),
        "run_id": run_id,
        "signals_count": len(actionable_signals),
        "index_candidates_count": len(index_candidates),
        "signal_contract_version": 2,
        "signal_qualification_basis": "VALIDATED_LONG_ENTRY_INTENT_OR_RISK_SIZED_CREDIT_PAPER_OPEN",
        "entry_event_count": entry_count,
        "entry_identity_status": entry_integrity,
        "closed_trades": len(closed),
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "fees_total": fees_total,
        "winning_trades": winning_trades if len(closed_with_pnl) == len(closed) else None,
        "losing_trades": losing_trades if len(closed_with_pnl) == len(closed) else None,
        "max_drawdown": round(max_drawdown, 2) if len(closed_with_pnl) == len(closed) and closed else None,
        "drawdown_basis": "REALIZED_CLOSED_TRADE_EQUITY",
        "pnl_coverage": len(closed_with_pnl),
        "trade_ledger": trade_ledger,
        "strategy_stats": strategy_stats,
        "rejected_count": len(rejected),
        "errors_count": len(errors),
        "events": recent,
        "rejection_events": [dict(time=str(e.get("timestamp") or e.get("time") or "")[:35], type=str(e.get("event") or ""), reason=str(e.get("reason") or e.get("message") or "")[:300], strategy=str(e.get("strategy") or ""), symbol=str(e.get("symbol") or "")) for e in rejected][-200:],
        "data_type": "PAPER_SIMULATION",
    }


def _firestore_field(value):
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_firestore_field(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _firestore_field(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def publish_history(data: dict, session=None) -> None:
    if session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
        session = AuthorizedSession(credentials)
    project = os.environ["FIREBASE_PROJECT_ID"]
    history_url = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/paper_history/{data['date_ist']}_{data['market']}"
    history = dict(data)  # Preserve diagnostic events in dated history.
    # Persist trade_ledger and its entry_strategy for historical per-strategy views.
    # Keep the ledger bounded in snapshot() to respect Firestore document limits.
    # Preserve the best verified journal across failed/restarted attempts.
    existing_response = session.get(history_url, timeout=25)
    if existing_response.status_code not in (200, 404):
        existing_response.raise_for_status()
    if existing_response.status_code == 200:
        def unpack(value):
            if "arrayValue" in value:
                return [unpack(v) for v in value["arrayValue"].get("values", [])]
            if "mapValue" in value:
                return {k: unpack(v) for k, v in value["mapValue"].get("fields", {}).items()}
            for kind in ("integerValue", "doubleValue", "stringValue", "booleanValue"):
                if kind in value:
                    return int(value[kind]) if kind == "integerValue" else value[kind]
            return None
        previous = {k: unpack(v) for k, v in existing_response.json().get("fields", {}).items()}
        old_ledger = previous.get("trade_ledger") or []
        new_ledger = history.get("trade_ledger") or []
        old_closed = int(previous.get("closed_trades") or 0)
        new_closed = int(history.get("closed_trades") or 0)
        # An interrupted restart must never erase previously published signals,
        # entries, closed trades, or rejection diagnostics. Prefer the older
        # verified snapshot if the new runner has incomplete restored history.
        old_coverage = (int(previous.get("signals_count") or 0),
                        int(previous.get("entry_event_count") or 0),
                        old_closed, int(previous.get("rejected_count") or 0),
                        len(old_ledger))
        new_coverage = (int(history.get("signals_count") or 0),
                        int(history.get("entry_event_count") or 0),
                        new_closed, int(history.get("rejected_count") or 0),
                        len(new_ledger))
        if any(old > new for old, new in zip(old_coverage, new_coverage)):
            history = dict(previous)
            history["last_attempt_status"] = data.get("session_status")
            history["last_attempt_at"] = data.get("updated_at")
            history["last_attempt_run_id"] = data.get("run_id")
    result = session.patch(history_url, json={"fields": {k: _firestore_field(v) for k, v in history.items()}}, timeout=25)
    result.raise_for_status()


def publish(data: dict) -> None:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(credentials)
    project = os.environ["FIREBASE_PROJECT_ID"]
    # Durable historical record first; latest is only a disposable read model.
    publish_history(data, session=session)
    url = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/paper_dashboard/latest_{data['market']}"
    response = session.patch(url, json={"fields": {k: _firestore_field(v) for k, v in data.items()}}, timeout=25)
    response.raise_for_status()


def loop(market: str, state_file: str, stop_file: str) -> None:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    consecutive_failures = 0
    while True:
        state = Path(state_file).read_text().strip() if Path(state_file).exists() else "STARTING"
        worker_file = ROOT / "trader" / ("worker_status_" + market + ".json")
        worker_result = None
        if worker_file.exists():
            try:
                candidate = json.loads(worker_file.read_text(encoding="utf-8"))
                if str(candidate.get("run_id")) == run_id:
                    worker_result = candidate
                    state = "FAILED" if candidate.get("exit_code") != 0 else "FINISHED"
            except (OSError, ValueError):
                pass
        if Path(stop_file).exists() and worker_result is None:
            state = "UNKNOWN" if state == "RUNNING" else state
        try:
            data = snapshot(market, state, run_id)
            if worker_result is not None:
                data["worker_exit_code"] = worker_result.get("exit_code")
                data["failure_reason"] = worker_result.get("failure_reason")
            publish(data)
            print("Private Firestore session snapshot updated", flush=True)
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            print("Firestore update failed:", type(exc).__name__, str(exc)[:160], flush=True)
            if consecutive_failures >= 3:
                raise RuntimeError("Firestore publisher failed three consecutive writes") from exc
        if Path(stop_file).exists():
            break
        time.sleep(30)


if __name__ == "__main__":
    loop(os.environ["PAPER_MARKET"], os.environ["PAPER_STATE_FILE"], os.environ["PAPER_STOP_FILE"])
