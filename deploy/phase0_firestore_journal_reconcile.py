"""T0 read-only ledger reconciliation. DO NOT print trade amounts or broker credentials.

Compares immutable private JSONL event aggregates to live Firestore paper_history.
No mutation, no data repair, no real orders. A mismatch is an incident, not zero.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

MARKETS = frozenset({"NIFTY", "SENSEX"})
REPOSITORY = "ambani5204/codex-trading-journals"
API = "https://api.github.com/repos/" + REPOSITORY
FILE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_(NIFTY|SENSEX)_[A-Za-z0-9_.-]+\.jsonl$")
MAX_PAGES = 3


def as_number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def summarize_events(events):
    signals = 0
    closes = 0
    coverage = 0
    net = 0.0
    summaries = 0
    for e in events:
        kind = e.get("event")
        if kind == "INDEX_SIGNAL":
            signals += 1
        elif kind == "SESSION_SUMMARY":
            summaries += 1
        elif kind == "PAPER_TRADE_CLOSED":
            closes += 1
            pnl = as_number(e.get("net_pnl"))
            if pnl is not None:
                coverage += 1
                net += pnl
    return {"signals": signals, "closed": closes, "coverage": coverage,
            "net": round(net, 2), "summaries": summaries}


def check_match(history, events, file_count):
    """No missing P&L is silently converted to zero. Return reason codes only."""
    if file_count == 0:
        return "MISSING_ARCHIVE"
    if history.get("data_type") != "PAPER_SIMULATION":
        return "UNSUPPORTED_DATA_TYPE"
    stats = summarize_events(events)
    closed = history.get("closed_trades")
    coverage = history.get("pnl_coverage")
    signals = history.get("signals_count")
    if any(not isinstance(n, int) or isinstance(n, bool)
           for n in (closed, coverage, signals)):
        return "MISSING_COUNTERS"
    if any(n < 0 for n in (closed, coverage, signals)) or coverage > closed:
        return "INVALID_HISTORY_COUNTERS"
    if closed != stats["closed"] or coverage != stats["coverage"] or signals != stats["signals"]:
        return "COUNTER_MISMATCH"
    observed = as_number(history.get("net_pnl"))
    if stats["coverage"] > 0 and observed is None:
        return "MISSING_HISTORY_PNL"
    if stats["coverage"] == 0 and observed is not None:
        return "UNEXPECTED_HISTORY_PNL"
    if observed is not None and abs(round(observed, 2) - stats["net"]) > 0.011:
        return "PNL_MISMATCH"
    if stats["closed"] > stats["coverage"]:
        return "PARTIAL_FINANCIAL_COVERAGE"
    # Matching counters do not establish that a session reached its terminal event.
    # Require at least one summary, but do not treat it as proof of correct shutdown.
    if stats["summaries"] == 0:
        return "MISSING_SESSION_SUMMARY"
    if stats["summaries"] > 1:
        return "AMBIGUOUS_SESSION_SUMMARIES"
    return "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED"


def duplicate_history_keys(rows):
    """Identify ambiguous date/market history without exposing financial values."""
    seen = set()
    duplicates = set()
    for row in rows:
        key = (str(row["date_ist"]), row["market"])
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def duplicate_history_metadata(rows):
    """Aggregate document identity diagnostics without exposing identifiers."""
    groups = defaultdict(list)
    for row in rows:
        groups[(str(row["date_ist"]), row["market"])].append(row.get("_document_name"))
    duplicates = [names for names in groups.values() if len(names) > 1]
    return {
        "groups": len(duplicates),
        "rows": sum(map(len, duplicates)),
        "missing_names": sum(not isinstance(n, str) or not n
                             for names in duplicates for n in names),
        "repeated_names": sum(len(names) - len(set(names)) for names in duplicates),
    }


def gh_get(token, path):
    if not path.startswith("/") or ".." in path or "?" in path:
        raise ValueError("Unsafe GitHub path")
    # Repository metadata endpoint is /repos/{owner}/{repo}, without a trailing slash.
    # A trailing slash can produce 404 even when the token is valid.
    url = API if path == "/" else API + path
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ALGOBANI-Phase0-ReadOnly-Audit",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read())


def load_archives(token, date):
    dt.date.fromisoformat(date)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("Invalid archive date")
    # Do not classify a 404 as an empty archive: it can also indicate
    # missing permissions, a renamed path, or a deleted archive.
    # Fail closed and preserve the HTTP status for incident triage.
    listing = gh_get(token, "/contents/journals/" + date)
    if not isinstance(listing, list):
        raise ValueError("Archive listing is not a directory")
    events = defaultdict(list)
    file_counts = defaultdict(int)
    for item in listing:
        name = item.get("name", "")
        matched = FILE_PATTERN.fullmatch(name)
        if not matched or not name.startswith(date + "_"):
            continue
        market = matched.group(1)
        data = gh_get(token, "/contents/journals/" + date + "/" +
                      urllib.parse.quote(name, safe=""))
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            raise ValueError("Unexpected archive file encoding")
        raw = base64.b64decode(data["content"], validate=False).decode("utf-8")
        file_counts[market] += 1
        for line in raw.splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("Archive line must be object")
                events[market].append(event)
    return {market: (events[market], file_counts[market]) for market in MARKETS}


def get_history():
    import google.oauth2.service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET"])
    creds = google.oauth2.service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/datastore"])
    session = AuthorizedSession(creds)
    base = ("https://firestore.googleapis.com/v1/projects/" +
            os.environ["FIREBASE_PROJECT_ID"] + "/databases/(default)/documents/paper_history")
    from deploy.nightly_strategy_evaluation import unpack
    rows = []
    next_token = None
    pages = 0
    while pages < MAX_PAGES:
        params = {"pageSize": 100}
        if next_token:
            params["pageToken"] = next_token
        response = session.get(base, params=params, timeout=25)
        response.raise_for_status()
        data = response.json()
        for entry in data.get("documents", []):
            row = {k: unpack(v) for k, v in entry.get("fields", {}).items()}
            # Internal provenance only; never log names, trades or financial values.
            row["_document_name"] = entry.get("name")
            rows.append(row)
        next_token = data.get("nextPageToken")
        pages += 1
        if not next_token:
            break
    if next_token:
        raise RuntimeError("History pagination bound exceeded; cannot claim full audit")
    return rows


def main():
    token = os.getenv("JOURNAL_REPO_TOKEN", "")
    if not token or not os.getenv("FIREBASE_SERVICE_ACCOUNT_STOCK_MARKET") or not os.getenv("FIREBASE_PROJECT_ID"):
        print("PHASE0_RECONCILIATION=UNAVAILABLE reason=MISSING_CONFIG", flush=True)
        return 2
    stage = "PRIVATE_REPO"
    try:
        meta = gh_get(token, "/")
        if meta.get("full_name", "").lower() != REPOSITORY.lower() or meta.get("private") is not True:
            raise ValueError("Private repository check failed")
        stage = "FIRESTORE_HISTORY"
        rows = get_history()
        targets = [r for r in rows if r.get("market") in MARKETS and r.get("date_ist")]
        if duplicate_history_keys(targets):
            meta = duplicate_history_metadata(targets)
            print("PHASE0_RECONCILIATION=BLOCKED reason=DUPLICATE_HISTORY_KEYS " +
                  "groups=" + str(meta["groups"]) + " rows=" + str(meta["rows"]) +
                  " missing_names=" + str(meta["missing_names"]) +
                  " repeated_names=" + str(meta["repeated_names"]), flush=True)
            return 4
        stage = "ARCHIVE_READ"
        archives = {date: load_archives(token, date)
                    for date in sorted({str(r["date_ist"]) for r in targets})}
        results = []
        for row in targets:
            day = str(row["date_ist"])
            market = row["market"]
            events, files = archives[day].get(market, ([], 0))
            reason = check_match(row, events, files)
            results.append(reason)
            print("RECONCILE_HISTORY date=" + day + " market=" + market +
                  " outcome=" + reason, flush=True)
        if not targets:
            print("PHASE0_RECONCILIATION=BLOCKED reason=NO_HISTORY", flush=True)
            return 4
        issues = [x for x in results if x != "COUNTS_MATCH_SESSION_TERMINATION_UNVERIFIED"]
        if issues:
            print("PHASE0_RECONCILIATION=INCOMPLETE records=" + str(len(results)) +
                  " unmatched=" + str(len(issues)) + " (no values logged)", flush=True)
            return 4
        print("PHASE0_RECONCILIATION=COUNTS_MATCH; SESSION_TERMINATION_AND_OPTIONS_FILLS_UNVERIFIED records=" +
              str(len(results)), flush=True)
        return 0
    except urllib.error.HTTPError as exc:
        print("PHASE0_RECONCILIATION=FAILED stage=" + stage +
              " http_status=" + str(exc.code), flush=True)
        return 3
    except Exception as exc:
        print("PHASE0_RECONCILIATION=FAILED stage=" + stage +
              " exception_type=" + type(exc).__name__,
              flush=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
