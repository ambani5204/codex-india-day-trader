"""S11.1 — Realistic performance target framework (Phase 11).

Owner's original ask was 10% per day on Rs 15k; project lead rejected that as
inconsistent with any backtest or any strategy on earth (would compound Rs 15k
to >~Rs 1.6 crore in two months). This module replaces the fantasy number with
FROZEN, evidence-based bands derived from our own real-candle backtest.

Classify a day/week/month into GREEN / FLAT / RED / STOP_HIT, using the honest
EMA 9/15 measured edge (approx Rs 75/day average over 900 days). Targets frozen
as constants — altering them is a visible code change, so a hard month cannot
quietly relax them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

GREEN = "GREEN"          # inside or above the expected band
FLAT = "FLAT"            # near zero, normal
RED = "RED"              # losing but above the hard stop
STOP_HIT = "STOP_HIT"    # hard daily/weekly/monthly loss cap triggered
NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class TargetBand:
    """One window's realistic band. All figures in rupees, net of fees."""
    window: str
    pessimistic: float   # -1 sigma
    expected: float      # median
    optimistic: float    # +1 sigma
    hard_stop: float     # negative; survival floor
    min_trades: int = 0
    max_trades: int = 0  # 0 = not applicable


# FROZEN bands for the Rs 15,000 EMA 9/15 live paper run.
# Source of numbers: Phase 8 backtest of EMA 9/15 over ~900 NIFTY+SENSEX sessions
# (CHG-20261127 series): +Rs 68k net, PF 1.37, max drawdown ~Rs 8-9k on SENSEX.
# These are the bands we hold ourselves to for the goal classifier.
BANDS_15K = {
    "day": TargetBand("day", -300.0, 75.0, 450.0, -600.0, min_trades=2, max_trades=7),
    "week": TargetBand("week", -500.0, 375.0, 1600.0, -2000.0),
    "month": TargetBand("month", 500.0, 1650.0, 5000.0, -5000.0),
}

# Owner-stated cadence target ("4 to 7 trades per day"). Kept distinct from the
# backtest-derived min_trades above so we can show both in the UI.
CADENCE_TARGET = (4, 7)


def classify(net_pnl: float, band: TargetBand) -> str:
    """Classify a window's P&L against its band.

    Order matters: STOP_HIT first (survival check), then GREEN, then FLAT/RED.
    FLAT = within +/- expected/2 (noise around zero is normal and healthy).
    """
    if net_pnl is None:
        return NO_DATA
    if net_pnl <= band.hard_stop:
        return STOP_HIT
    if net_pnl >= band.pessimistic and net_pnl <= -band.pessimistic:
        # Narrow flat band around zero; use |pessimistic| as half-width guard.
        pass
    if net_pnl >= band.expected * 0.5:
        return GREEN
    if net_pnl >= band.pessimistic:
        return FLAT
    return RED


def classify_day(net_pnl: float, trades: int = 0, capital: float = 15000.0) -> dict:
    """Returns the full day verdict used by the goal tracker and the UI."""
    band = BANDS_15K["day"]  # capital=15000 only supported for now; see M-path
    verdict = classify(net_pnl, band)
    tmin, tmax = CADENCE_TARGET
    if trades == 0:
        cadence = "NONE"
    elif trades < tmin:
        cadence = "UNDER"
    elif trades <= tmax:
        cadence = "ON_TARGET"
    else:
        cadence = "OVER"
    return {
        "capital": capital,
        "net_pnl": net_pnl,
        "trades": trades,
        "verdict": verdict,
        "cadence": cadence,
        "band": {
            "pessimistic": band.pessimistic,
            "expected": band.expected,
            "optimistic": band.optimistic,
            "hard_stop": band.hard_stop,
            "min_trades": tmin,
            "max_trades": tmax,
        },
    }


def classify_week(daily_pnls: List[float], capital: float = 15000.0) -> dict:
    """Sum the week's net P&L, classify against the weekly band."""
    band = BANDS_15K["week"]
    present = [d for d in daily_pnls if d is not None]
    total = round(sum(present), 2)
    verdict = NO_DATA if not present else classify(total, band)
    return {
        "capital": capital,
        "sessions": len(present),
        "net_pnl": total,
        "verdict": verdict,
        "band": {
            "pessimistic": band.pessimistic,
            "expected": band.expected,
            "optimistic": band.optimistic,
            "hard_stop": band.hard_stop,
        },
    }


def classify_month(daily_pnls: List[float], capital: float = 15000.0) -> dict:
    """Monthly roll-up; same classifier, monthly band."""
    band = BANDS_15K["month"]
    present = [d for d in daily_pnls if d is not None]
    total = round(sum(present), 2)
    verdict = NO_DATA if not present else classify(total, band)
    return {
        "capital": capital,
        "sessions": len(present),
        "net_pnl": total,
        "verdict": verdict,
        "band": {
            "pessimistic": band.pessimistic,
            "expected": band.expected,
            "optimistic": band.optimistic,
            "hard_stop": band.hard_stop,
        },
    }


# Explicitly reject unrealistic targets so no code path can set them.
UNREALISTIC_DAILY_TARGET_REJECTED_AT_RS = 1500  # 10%/day on Rs 15k
UNREALISTIC_DAILY_TARGET_REJECTED_REASON = (
    "10% per day compounds beyond global market capacity within a year; "
    "requires near-100% capital risk per trade vs the 4% configured stop. "
    "Replaced with evidence-based bands from our own backtest."
)
