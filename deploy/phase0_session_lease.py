"""Phase 0 paper-only canonical session lease: Firestore CAS prototype.

This module is deliberately NOT imported by a cloud worker or publisher.
No credentials are created here. ALL operations require an injected client.
A lease alone does not fence downstream journal/Firestore writes: integration
must add atomic generation validation to every persisted event before release.
Do not auto-reclaim stale/expired owners without verified journal recovery.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
from dataclasses import dataclass

from india_trader.core import IST

PROJECT = "stock-market-c5016"
COLLECTION = "paper_session_leases_v1"
API_ROOT = ("https://firestore.googleapis.com/v1/projects/" + PROJECT
            + "/databases/(default)")
DB_RESOURCE = "projects/" + PROJECT + "/databases/(default)"
MARKETS = frozenset({"NIFTY", "SENSEX"})
ATTEMPT_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATES = frozenset({"ACTIVE"})  # Future states require an explicit migration.
UTC = dt.timezone.utc


class LeaseBlocked(RuntimeError):
    """Contended, expired, malformed, or otherwise unsafe ownership."""


class LeaseUnavailable(RuntimeError):
    """Remote response did not establish a usable atomic ownership result."""


@dataclass(frozen=True)
class Lease:
    date_ist: str
    market: str
    owner_attempt_id: str
    strategy_version: str
    lease_id: str
    generation: int
    created_at: str
    expires_at: str
    update_time: str
    state: str = "ACTIVE"


def _time(value: dt.datetime) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValueError("An aware UTC/IST timestamp is required")
    return value.astimezone(UTC)


def _stamp(value: dt.datetime) -> str:
    return _time(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_stamp(value: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LeaseBlocked("MALFORMED_TIMESTAMP")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Naive timestamp")
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LeaseBlocked("MALFORMED_TIMESTAMP") from exc


def _identity(date_ist: str, market: str, attempt_id: str, version: str) -> None:
    if not isinstance(date_ist, str) or not ISO_DATE_RE.fullmatch(date_ist):
        raise ValueError("INVALID_IST_DATE")
    if dt.date.fromisoformat(date_ist).isoformat() != date_ist:
        raise ValueError("INVALID_IST_DATE")
    if market not in MARKETS:
        raise ValueError("UNSUPPORTED_MARKET")
    if not isinstance(attempt_id, str) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise ValueError("INVALID_ATTEMPT_ID")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError("INVALID_STRATEGY_VERSION")


def document_name(date_ist: str, market: str) -> str:
    # Canonical key excludes run/strategy version so restarts cannot create
    # parallel session owners for the same trading date and market.
    _identity(date_ist, market, "validation", "validation")
    return DB_RESOURCE + "/documents/" + COLLECTION + "/" + date_ist + "_" + market


def _fields(lease: Lease) -> dict:
    result = {}
    for key in ("date_ist", "market", "owner_attempt_id", "strategy_version",
                "lease_id", "created_at", "expires_at", "state"):
        result[key] = {"stringValue": getattr(lease, key)}
    result["generation"] = {"integerValue": str(lease.generation)}
    return result


def _read_lease(doc: dict, date_ist: str, market: str) -> Lease:
    name = document_name(date_ist, market)
    if not isinstance(doc, dict) or doc.get("name") != name:
        raise LeaseBlocked("WRONG_DOCUMENT_IDENTITY")
    fields = doc.get("fields")
    if not isinstance(fields, dict):
        raise LeaseBlocked("MISSING_LEASE_FIELDS")
    values = {}
    for key in ("date_ist", "market", "owner_attempt_id", "strategy_version",
                "lease_id", "created_at", "expires_at", "state"):
        value = fields.get(key)
        if not isinstance(value, dict) or not isinstance(value.get("stringValue"), str):
            raise LeaseBlocked("MISSING_OR_INVALID_" + key.upper())
        values[key] = value["stringValue"]
    gen = fields.get("generation")
    if not isinstance(gen, dict) or not isinstance(gen.get("integerValue"), str):
        raise LeaseBlocked("MISSING_GENERATION")
    try:
        generation = int(gen["integerValue"])
    except ValueError as exc:
        raise LeaseBlocked("INVALID_GENERATION") from exc
    update = doc.get("updateTime")
    if not isinstance(update, str):
        raise LeaseBlocked("MISSING_UPDATE_TIME")
    _parse_stamp(update)
    _parse_stamp(values["created_at"])
    _parse_stamp(values["expires_at"])
    if (values["date_ist"] != date_ist or values["market"] != market
            or generation < 1 or values["state"] not in STATES
            or _parse_stamp(values["created_at"]) >= _parse_stamp(values["expires_at"])):
        raise LeaseBlocked("INCONSISTENT_LEASE_RECORD")
    try:
        _identity(date_ist, market, values["owner_attempt_id"],
                  values["strategy_version"])
    except ValueError as exc:
        raise LeaseBlocked("MALFORMED_LEASE_IDENTITY") from exc
    if not re.fullmatch(r"[0-9a-f]{32}", values["lease_id"]):
        raise LeaseBlocked("INVALID_FENCE_TOKEN")
    return Lease(**values, generation=generation, update_time=update)


def _commit(session, lease: Lease, precondition: dict) -> str:
    # Firestore Commit's writes are atomic; currentDocument is an enforced CAS.
    # No automatic HTTP retry: ambiguous request completion must fail closed.
    body = {"writes": [{
        "update": {"name": document_name(lease.date_ist, lease.market),
                   "fields": _fields(lease)},
        "currentDocument": precondition,
    }]}
    try:
        reply = session.post(API_ROOT + "/documents:commit", json=body, timeout=25)
    except Exception as exc:
        raise LeaseUnavailable("COMMIT_OUTCOME_UNKNOWN") from exc
    if reply.status_code in (409, 412):
        raise LeaseBlocked("CAS_CONFLICT")
    if reply.status_code != 200:
        raise LeaseUnavailable("COMMIT_FAILED_HTTP_" + str(reply.status_code))
    try:
        result = reply.json()
        results = result["writeResults"]
        stamp = results[0]["updateTime"]
        if len(results) != 1:
            raise ValueError("Unexpected write count")
        _parse_stamp(stamp)
        return stamp
    except (KeyError, IndexError, TypeError, ValueError, LeaseBlocked) as exc:
        raise LeaseUnavailable("COMMIT_ACK_UNVERIFIED") from exc


def inspect(session, date_ist: str, market: str) -> Lease | None:
    """GET-only; an unexpected HTTP response must never imply no owner."""
    name = document_name(date_ist, market)
    try:
        response = session.get("https://firestore.googleapis.com/v1/" + name,
                               timeout=25)
    except Exception as exc:
        raise LeaseUnavailable("LEASE_READ_FAILED") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise LeaseUnavailable("LEASE_READ_HTTP_" + str(response.status_code))
    try:
        return _read_lease(response.json(), date_ist, market)
    except (ValueError, TypeError, KeyError) as exc:
        raise LeaseBlocked("MALFORMED_LEASE_RECORD") from exc


def acquire(session, date_ist: str, market: str, owner_attempt_id: str,
            strategy_version: str, *, now: dt.datetime,
            ttl_seconds: int = 120) -> Lease:
    """Create-if-absent; NEVER overwrite an existing lease even after expiry."""
    _identity(date_ist, market, owner_attempt_id, strategy_version)
    current = _time(now)
    if current.astimezone(IST).date().isoformat() != date_ist:
        raise LeaseBlocked("NOT_CURRENT_IST_SESSION_DATE")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 300:
        raise ValueError("INVALID_TTL")
    provisional = Lease(date_ist=date_ist, market=market,
                        owner_attempt_id=owner_attempt_id,
                        strategy_version=strategy_version,
                        lease_id=secrets.token_hex(16), generation=1,
                        created_at=_stamp(current),
                        expires_at=_stamp(current + dt.timedelta(seconds=ttl_seconds)),
                        update_time="", state="ACTIVE")
    update_time = _commit(session, provisional, {"exists": False})
    return Lease(**{**vars(provisional), "update_time": update_time})


def heartbeat(session, lease: Lease, *, now: dt.datetime,
              ttl_seconds: int = 120) -> Lease:
    """Extend only the current owner with CAS; no resurrection after TTL."""
    current = _time(now)
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 300:
        raise ValueError("INVALID_TTL")
    observed = inspect(session, lease.date_ist, lease.market)
    if observed is None:
        raise LeaseBlocked("LEASE_DISAPPEARED")
    if (observed.owner_attempt_id != lease.owner_attempt_id
            or observed.lease_id != lease.lease_id
            or observed.generation != lease.generation
            or observed.strategy_version != lease.strategy_version
            or observed.update_time != lease.update_time
            or observed.state != "ACTIVE"):
        raise LeaseBlocked("LOST_FENCE_OR_STALE_READ")
    if current < _parse_stamp(observed.created_at):
        raise LeaseBlocked("CLOCK_REGRESSION")
    if current >= _parse_stamp(observed.expires_at):
        raise LeaseBlocked("LEASE_EXPIRED_RECONCILIATION_REQUIRED")
    new = Lease(**{**vars(observed),
                   "expires_at": _stamp(current + dt.timedelta(seconds=ttl_seconds))})
    stamp = _commit(session, new, {"updateTime": observed.update_time})
    return Lease(**{**vars(new), "update_time": stamp})


def deny_automatic_takeover(*_args, **_kwargs) -> None:
    """An expired lease is not evidence of absent paper positions or fills."""
    raise LeaseBlocked("EXPLICIT_JOURNAL_RECONCILIATION_AND_WRITER_FENCING_REQUIRED")
