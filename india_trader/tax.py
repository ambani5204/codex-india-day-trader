"""F&O income tax layer (Phase 4).

Index option trading P&L in India is non-speculative BUSINESS income, taxed at
the individual's SLAB rate (not a flat STCG rate). Per-trade transaction costs
(brokerage, STT, exchange, SEBI, GST, stamp) are already modelled in
paper_sim.option_fees; those are deductible business expenses, so this layer
applies tax on NET P&L (after fees).

Important honesty notes:
  * Actual tax depends on the trader's TOTAL income from all sources and chosen
    regime — this cannot be known from trading P&L alone. The function therefore
    takes other_income and regime explicitly.
  * Slabs are the FY2025-26 (AY2026-27) NEW regime defaults, which I state with
    the caveat that the user should confirm against the current Finance Act /
    their CA before relying on them for filing. They are parameterised so a wrong
    default can be overridden without code changes.
  * A trading LOSS produces zero tax here (set-off/carry-forward of business
    losses is a filing matter, not modelled).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# FY2025-26 new-regime slabs (annual, INR). VERIFY against the current Finance Act.
NEW_REGIME_FY2526: List[Tuple[float, float]] = [
    (400_000, 0.00),
    (800_000, 0.05),
    (1_200_000, 0.10),
    (1_600_000, 0.15),
    (2_000_000, 0.20),
    (2_400_000, 0.25),
    (float("inf"), 0.30),
]
CESS = 0.04  # health & education cess on tax


@dataclass
class TaxResult:
    trading_net: float
    taxable_income: float
    tax_before_cess: float
    cess: float
    total_tax: float
    effective_rate_on_trading: float
    note: str = field(default="")


def _slab_tax(income: float, slabs) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        if income > lower:
            tax += (min(income, upper) - lower) * rate
            lower = upper
        else:
            break
    return tax


def fno_tax(trading_net: float, other_income: float = 0.0,
            slabs=NEW_REGIME_FY2526, cess: float = CESS) -> TaxResult:
    """Marginal tax attributable to F&O trading net P&L (after fees).

    Computed as tax(other_income + trading_net) - tax(other_income), so it is the
    *extra* tax the trading adds on top of the trader's other income.
    """
    if trading_net <= 0:
        return TaxResult(trading_net, max(other_income, 0.0), 0.0, 0.0, 0.0, 0.0,
                         "Trading loss/zero: no tax modelled (set-off is a filing matter).")
    base = _slab_tax(max(other_income, 0.0), slabs)
    withtrade = _slab_tax(max(other_income, 0.0) + trading_net, slabs)
    marginal = withtrade - base
    total = marginal * (1 + cess)
    eff = total / trading_net if trading_net else 0.0
    return TaxResult(
        trading_net=trading_net,
        taxable_income=max(other_income, 0.0) + trading_net,
        tax_before_cess=round(marginal, 2),
        cess=round(marginal * cess, 2),
        total_tax=round(total, 2),
        effective_rate_on_trading=round(eff, 4),
        note="Marginal tax on trading P&L over other_income; new-regime FY25-26 defaults — verify with a CA.",
    )


def net_after_tax(trading_net: float, other_income: float = 0.0, **kw) -> float:
    return round(trading_net - fno_tax(trading_net, other_income, **kw).total_tax, 2)
