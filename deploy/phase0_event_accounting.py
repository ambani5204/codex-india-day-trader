"""Synthetic/offline only. Never prints private event IDs or monetary values."""
from collections import Counter
from decimal import Decimal, InvalidOperation

def audit_event_accounting(sessions, journal_events, firestore_events):
    """Fail closed on identity, foreign keys, and after-cost closed-trade coverage.

    Both event inputs must be independently extracted; equality here cannot
    authenticate provenance or establish that either extraction is complete.
    """
    if not isinstance(sessions, (list, tuple)) or not sessions:
        return {"ok": False, "reason": "MISSING_SESSION_MANIFEST"}
    keys = set()
    for row in sessions:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k].strip() for k in ("session_id", "run_id")):
            return {"ok": False, "reason": "INVALID_SESSION_MANIFEST"}
        key = (row["session_id"], row["run_id"])
        if key in keys:
            return {"ok": False, "reason": "DUPLICATE_SESSION"}
        keys.add(key)

    def inspect(events, source):
        if not isinstance(events, (list, tuple)):
            return None, source + "_MISSING_EVENTS"
        identities = []
        for row in events:
            if not isinstance(row, dict):
                return None, source + "_INVALID_EVENT"
            kind = row.get("kind")
            if kind not in ("SIGNAL", "CLOSED_TRADE"):
                return None, source + "_UNKNOWN_KIND"
            if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("event_id", "session_id", "run_id")):
                return None, source + "_MISSING_IDENTITY"
            if (row["session_id"], row["run_id"]) not in keys:
                return None, source + "_ORPHAN_EVENT"
            identity = (row["session_id"], row["run_id"], kind, row["event_id"])
            if kind == "CLOSED_TRADE":
                if not isinstance(row.get("trade_id"), str) or not row["trade_id"].strip():
                    return None, source + "_MISSING_TRADE_ID"
                try:
                    gross = Decimal(str(row["gross_pnl"]))
                    fees = Decimal(str(row["total_costs"]))
                    net = Decimal(str(row["net_pnl"]))
                except (KeyError, InvalidOperation, ValueError, TypeError):
                    return None, source + "_MISSING_PNL_COVERAGE"
                if not all(v.is_finite() for v in (gross, fees, net)) or fees < 0:
                    return None, source + "_INVALID_PNL"
                if gross - fees != net:
                    return None, source + "_AFTER_COST_MISMATCH"
                identity += (row["trade_id"], str(gross), str(fees), str(net))
            identities.append(identity)
        event_keys = [(x[0], x[1], x[2], x[3]) for x in identities]
        if len(event_keys) != len(set(event_keys)):
            return None, source + "_DUPLICATE_EVENT"
        trades = [(x[0], x[1], x[4]) for x in identities if x[2] == "CLOSED_TRADE"]
        if len(trades) != len(set(trades)):
            return None, source + "_DUPLICATE_TRADE"
        return Counter(identities), None

    left, error = inspect(journal_events, "JOURNAL")
    if error:
        return {"ok": False, "reason": error}
    right, error = inspect(firestore_events, "FIRESTORE")
    if error:
        return {"ok": False, "reason": error}
    if left != right:
        return {"ok": False, "reason": "EVENT_OR_ACCOUNTING_MISMATCH"}
    return {"ok": True, "reason": "SUPPLIED_EVENTS_MATCH_ONLY"}
