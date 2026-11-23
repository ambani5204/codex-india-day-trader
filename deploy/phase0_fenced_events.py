"""Atomic append-only *paper* event + CAS session fence (isolated Phase 0 draft).

NOT CONNECTED to the paper workers, journal, publishers, or GitHub workflow.
Every call requires an injected Firestore client; no credentials are loaded.
The two Firestore Commit writes succeed or fail together:
  1. compare-and-swap the exact canonical market/date lease version;
  2. create an immutable paper event document (exists=false).

An expired/unknown/stolen lease must never generate a new event. This does
not guard legacy JSONL and Firestore PATCH writers; release integration must
replace those paths and pass a real restart/restore/clock acceptance suite.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, replace

from . import phase0_session_lease as ownership

EVENTS = frozenset({"PAPER_BUY_FILLED", "PAPER_SPREAD_OPEN", "PAPER_TRADE_CLOSED"})
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
INSTRUMENT_RE = re.compile(r"^[A-Za-z0-9_|:./-]{1,180}$")
COLLECTION = "paper_events_v1"
MIN_EXPIRY_HEADROOM_SECONDS = 10


class EventRejected(ownership.LeaseBlocked):
    """Invalid event lineage or non-actionable, inconsistent options fill."""


@dataclass(frozen=True)
class PaperEvent:
    event_id: str                 # Stable across retry/replay, NOT generated here.
    event_kind: str               # Real paper fill/close only, never INDEX_SIGNAL.
    date_ist: str
    market: str
    session_id: str               # Stable canonical session identity.
    strategy_id: str
    strategy_version: str
    instrument_key: str
    option_type: str              # CE or PE, including defined-risk credit side.
    quantity: int
    fill_price: float             # Observed hypothetical option bid/ask, >0.
    occurred_at: str             # UTC ISO instant, not an index detection time.
    hedge_instrument_key: str = ""
    open_event_id: str = ""      # Required for a closed paper position.
    gross_pnl: float | None = None
    fees_total: float | None = None
    net_pnl: float | None = None


def _money(value: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise EventRejected("NONFINITE_FINANCIAL_VALUE")
    return float(value)


def _event_name(event: PaperEvent) -> str:
    if not isinstance(event.event_id, str) or not ID_RE.fullmatch(event.event_id):
        raise EventRejected("INVALID_EVENT_ID")
    return (ownership.DB_RESOURCE + "/documents/" + COLLECTION + "/"
            + event.date_ist + "_" + event.market + "_" + event.event_id)


def _validate(event: PaperEvent, lease: ownership.Lease, now: dt.datetime) -> None:
    if not isinstance(event, PaperEvent):
        raise EventRejected("INVALID_EVENT_TYPE")
    _event_name(event)
    if event.date_ist != lease.date_ist or event.market != lease.market:
        raise EventRejected("WRONG_MARKET_OR_DATE")
    if event.strategy_version != lease.strategy_version:
        raise EventRejected("STRATEGY_VERSION_DRIFT")
    if event.event_kind not in EVENTS:
        raise EventRejected("NOT_A_PAPER_FILL_EVENT")
    if (not isinstance(event.session_id, str) or not ID_RE.fullmatch(event.session_id)
            or not isinstance(event.strategy_id, str)
            or not ID_RE.fullmatch(event.strategy_id)):
        raise EventRejected("MISSING_EVENT_LINEAGE")
    if event.option_type not in ("CE", "PE"):
        raise EventRejected("NOT_CE_PE_OPTIONS")
    if (not isinstance(event.instrument_key, str)
            or not INSTRUMENT_RE.fullmatch(event.instrument_key)):
        raise EventRejected("MISSING_OPTION_INSTRUMENT")
    if (isinstance(event.quantity, bool) or not isinstance(event.quantity, int)
            or event.quantity <= 0):
        raise EventRejected("INVALID_OPTION_QUANTITY")
    if _money(event.fill_price) <= 0:
        raise EventRejected("INVALID_OPTION_FILL_PRICE")
    event_time = ownership._parse_stamp(event.occurred_at)
    instant = ownership._time(now)
    if (event_time.astimezone(ownership.IST).date().isoformat() != event.date_ist
            or event_time > instant + dt.timedelta(seconds=5)):
        raise EventRejected("UNTRUSTED_EVENT_TIMESTAMP")
    if event.event_kind == "PAPER_SPREAD_OPEN":
        if (not isinstance(event.hedge_instrument_key, str)
                or not INSTRUMENT_RE.fullmatch(event.hedge_instrument_key)
                or event.hedge_instrument_key == event.instrument_key):
            raise EventRejected("CREDIT_SPREAD_HEDGE_REQUIRED")
    elif event.hedge_instrument_key:
        raise EventRejected("UNEXPECTED_HEDGE_INSTRUMENT")
    if event.event_kind == "PAPER_TRADE_CLOSED":
        if (not isinstance(event.open_event_id, str)
                or not ID_RE.fullmatch(event.open_event_id)
                or event.open_event_id == event.event_id):
            raise EventRejected("CLOSE_WITHOUT_OPEN_EVENT_ID")
        gross = _money(event.gross_pnl)
        fees = _money(event.fees_total)
        net = _money(event.net_pnl)
        if fees < 0 or abs(round(gross - fees, 2) - round(net, 2)) > 0.011:
            raise EventRejected("AFTER_COST_PNL_MISMATCH")
    elif (event.open_event_id or any(x is not None
                                     for x in (event.gross_pnl, event.fees_total,
                                               event.net_pnl))):
        raise EventRejected("ENTRY_CANNOT_CLAIM_CLOSED_PNL")


def _fields(event: PaperEvent, lease: ownership.Lease) -> dict:
    result = {}
    for name in ("event_id", "event_kind", "date_ist", "market", "session_id",
                 "strategy_id", "strategy_version", "instrument_key",
                 "option_type", "occurred_at", "hedge_instrument_key",
                 "open_event_id"):
        result[name] = {"stringValue": getattr(event, name)}
    for name in ("quantity",):
        result[name] = {"integerValue": str(getattr(event, name))}
    result["fill_price"] = {"doubleValue": float(event.fill_price)}
    for name in ("gross_pnl", "fees_total", "net_pnl"):
        value = getattr(event, name)
        result[name] = ({"doubleValue": float(value)} if value is not None
                        else {"nullValue": None})
    result.update({
        "paper_only": {"booleanValue": True},
        "order_source": {"stringValue": "UPSTOX_READ_ONLY_SIMULATION"},
        "owner_attempt_id": {"stringValue": lease.owner_attempt_id},
        "lease_id": {"stringValue": lease.lease_id},
        "lease_generation": {"integerValue": str(lease.generation)},
    })
    return result


def append_once(client, lease: ownership.Lease, event: PaperEvent,
                *, now: dt.datetime) -> ownership.Lease:
    """Fenced append. A failed/unknown ACK MUST NOT be retried blindly.

    External replay must first GET the exact immutable event ID, compare its
    content/hash to the source journal and lease lineage, and adjudicate.
    """
    instant = ownership._time(now)
    if not isinstance(lease, ownership.Lease):
        raise EventRejected("MISSING_OWNER_LEASE")
    _validate(event, lease, instant)
    observed = ownership.inspect(client, lease.date_ist, lease.market)
    if observed is None:
        raise EventRejected("NO_CANONICAL_LEASE")
    if observed != lease or observed.state != "ACTIVE":
        raise EventRejected("LOST_FENCE_OR_STALE_OWNER")
    if instant < ownership._parse_stamp(lease.created_at):
        raise EventRejected("CLOCK_REGRESSION")
    if instant + dt.timedelta(seconds=MIN_EXPIRY_HEADROOM_SECONDS) >= ownership._parse_stamp(lease.expires_at):
        raise EventRejected("LEASE_TOO_CLOSE_TO_EXPIRY")
    if lease.generation <= 0:
        raise EventRejected("INVALID_LEASE_GENERATION")

    writes = [
        {
            "update": {"name": ownership.document_name(lease.date_ist, lease.market),
                       "fields": ownership._fields(lease)},
            "currentDocument": {"updateTime": lease.update_time},
        },
        {
            "update": {"name": _event_name(event), "fields": _fields(event, lease)},
            "currentDocument": {"exists": False},
        },
    ]
    try:
        reply = client.post(ownership.API_ROOT + "/documents:commit",
                            json={"writes": writes}, timeout=25)
    except Exception as exc:
        raise ownership.LeaseUnavailable("FENCED_EVENT_COMMIT_UNKNOWN") from exc
    if reply.status_code in (409, 412):
        raise EventRejected("FENCED_EVENT_CAS_OR_DUPLICATE_CONFLICT")
    if reply.status_code != 200:
        raise ownership.LeaseUnavailable("FENCED_EVENT_COMMIT_HTTP_" + str(reply.status_code))
    try:
        response = reply.json()
        results = response["writeResults"]
        if len(results) != 2:
            raise ValueError("Unexpected number of writes")
        lease_update = results[0]["updateTime"]
        event_update = results[1]["updateTime"]
        ownership._parse_stamp(lease_update)
        ownership._parse_stamp(event_update)
    except (IndexError, KeyError, TypeError, ValueError, ownership.LeaseBlocked) as exc:
        raise ownership.LeaseUnavailable("FENCED_EVENT_ACK_UNVERIFIED") from exc
    return replace(lease, update_time=lease_update)


def verify_persisted_event(client, lease: ownership.Lease, event: PaperEvent) -> str:
    """GET-only adjudication after an ambiguous commit; never retries writes.

    An exact private document match proves this immutable event was persisted,
    not that it has a valid matched closing/opening trade or that Firestore
    matches the external JSONL ledger. Missing data is UNKNOWN, not zero.
    """
    if not isinstance(lease, ownership.Lease):
        raise EventRejected("MISSING_OWNER_LEASE")
    _validate(event, lease, ownership._parse_stamp(event.occurred_at))
    url = "https://firestore.googleapis.com/v1/" + _event_name(event)
    try:
        response = client.get(url, timeout=25)
    except Exception as exc:
        raise ownership.LeaseUnavailable("EVENT_READ_UNAVAILABLE") from exc
    if response.status_code == 404:
        return "EVENT_ABSENT_UNVERIFIED"
    if response.status_code != 200:
        raise ownership.LeaseUnavailable("EVENT_READ_HTTP_" + str(response.status_code))
    try:
        document = response.json()
        if (not isinstance(document, dict)
                or document.get("name") != _event_name(event)
                or not isinstance(document.get("fields"), dict)):
            raise EventRejected("EVENT_DOCUMENT_IDENTITY_INVALID")
        ownership._parse_stamp(document.get("updateTime"))
        if document["fields"] != _fields(event, lease):
            raise EventRejected("EVENT_SOURCE_LINEAGE_OR_PAYLOAD_MISMATCH")
    except (KeyError, TypeError, ValueError, ownership.LeaseBlocked) as exc:
        if isinstance(exc, EventRejected):
            raise
        raise EventRejected("EVENT_DOCUMENT_MALFORMED") from exc
    return "EVENT_PERSISTED_EXACT_MATCH"
