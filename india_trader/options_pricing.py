"""Black-Scholes option pricing + greeks for ALGOBANI (strategy-spec-dhansetu-v1).

Dependency-free (math only). Used for:
- forward paper: sanity-check observed premiums / estimate delta for ATM selection,
- clearly-labelled MODEL/scenario analysis (e.g. theta decay over a hold),
NEVER as a substitute for real historical premiums in a backtest.

European options, no dividend (index options). r is the annual risk-free rate;
sigma is annualised IV; t is time to expiry in YEARS.
"""
from __future__ import annotations

import math

SQRT2 = math.sqrt(2.0)
MINUTES_PER_YEAR = 365.0 * 24 * 60


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(spot, strike, t, r, sigma):
    if t <= 0 or sigma <= 0:
        return None, None
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return d1, d2


def price(spot, strike, t, r, sigma, call=True):
    """Black-Scholes premium. At/after expiry returns intrinsic value."""
    if t <= 0:
        return max(0.0, (spot - strike) if call else (strike - spot))
    d1, d2 = _d1_d2(spot, strike, t, r, sigma)
    if call:
        return spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def delta(spot, strike, t, r, sigma, call=True):
    d1, _ = _d1_d2(spot, strike, t, r, sigma)
    if d1 is None:
        return None
    return _norm_cdf(d1) if call else _norm_cdf(d1) - 1.0


def gamma(spot, strike, t, r, sigma):
    d1, _ = _d1_d2(spot, strike, t, r, sigma)
    if d1 is None:
        return None
    return _norm_pdf(d1) / (spot * sigma * math.sqrt(t))


def vega(spot, strike, t, r, sigma):
    """Per 1.00 (100%) change in IV. Divide by 100 for per-1%-IV."""
    d1, _ = _d1_d2(spot, strike, t, r, sigma)
    if d1 is None:
        return None
    return spot * _norm_pdf(d1) * math.sqrt(t)


def theta_per_day(spot, strike, t, r, sigma, call=True):
    """Calendar theta per DAY (premium points lost to decay per day), negative."""
    d1, d2 = _d1_d2(spot, strike, t, r, sigma)
    if d1 is None:
        return 0.0
    term1 = -(spot * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(t))
    if call:
        term2 = -r * strike * math.exp(-r * t) * _norm_cdf(d2)
    else:
        term2 = r * strike * math.exp(-r * t) * _norm_cdf(-d2)
    return (term1 + term2) / 365.0


def decay_over_minutes(spot, strike, r, sigma, minutes_held, days_to_expiry, call=True):
    """Approx premium lost to theta over an intraday hold (positive = points lost).

    Prices at entry vs after `minutes_held` with spot unchanged (pure time decay).
    """
    t0 = max(days_to_expiry, 1e-6) / 365.0
    t1 = max(days_to_expiry - minutes_held / (24 * 60), 1e-6) / 365.0
    p0 = price(spot, strike, t0, r, sigma, call)
    p1 = price(spot, strike, t1, r, sigma, call)
    return max(0.0, p0 - p1)
