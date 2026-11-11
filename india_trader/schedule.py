"""Weekday market selection for paper trading (not an exchange holiday calendar).

NIFTY weekly options normally expire Tuesdays, SENSEX Thursdays.
Avoid same-day-expiry positions because this engine lacks exercise/settlement modeling.
The *actual* eligible option expiry is resolved from today's exchange instrument master.
"""
from __future__ import annotations
import datetime as dt

WEEKDAY_MARKET = ('NIFTY', 'NIFTY', 'SENSEX', 'SENSEX', 'NIFTY')

def market_for_day(day: dt.date) -> str | None:
    """Mon/Tue NIFTY, Wed/Thu SENSEX, Fri NIFTY, weekends none."""
    weekday = day.weekday()
    return WEEKDAY_MARKET[weekday] if weekday < 5 else None
