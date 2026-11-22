#!/usr/bin/env python3
"""One-shot Upstox real API order test. No retries, no unattended submission."""
import json
import os
import sys
import urllib.error
import urllib.request

def main():
    key = os.environ.get("UPSTOX_INSTRUMENT_KEY", "").strip()
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    qty = int(os.environ.get("ORDER_QUANTITY", "65"))
    price = float(os.environ.get("ORDER_LIMIT_PRICE", "0.55"))
    submit = os.environ.get("SUBMIT_REAL_ORDER", "false").lower() == "true"
    confirmation = os.environ.get("ORDER_CONFIRMATION", "")
    if not key or qty <= 0 or price <= 0:
        raise SystemExit("Missing instrument key or invalid quantity/price; no order sent")
    if qty != 65 or price != 0.55:
        raise SystemExit("This test is locked to 65 quantity and 0.55 limit; no order sent")
    payload = {
        "quantity": qty, "product": "D", "validity": "DAY",
        "price": price, "instrument_token": key, "order_type": "LIMIT",
        "transaction_type": "BUY", "disclosed_quantity": 0,
        "trigger_price": 0, "is_amo": True, "slice": False,
        "market_protection": 0, "tag": "MANUAL_AMO_TEST"
    }
    print("Order intent:", json.dumps({**payload, "instrument_token": "[configured]"}, indent=2))
    if not submit:
        print("DRY RUN: no order submitted")
        return
    if confirmation != "PLACE_REAL_ORDER_27550_CE_65_055":
        raise SystemExit("Confirmation mismatch; no order submitted")
    if not token:
        raise SystemExit("Missing UPSTOX_ACCESS_TOKEN secret; no order submitted")
    req = urllib.request.Request(
        "https://api-hft.upstox.com/v3/order/place",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print("HTTP status:", resp.status)
            print("Broker response:", resp.read().decode("utf-8")[:3000])
    except urllib.error.HTTPError as exc:
        print("Broker rejected request; HTTP", exc.code)
        print(exc.read().decode("utf-8")[:3000])
        raise SystemExit(1)
    except Exception:
        print("Request outcome unknown. Check Upstox orders before any retry; do NOT resubmit automatically.")
        raise

if __name__ == "__main__":
    main()
