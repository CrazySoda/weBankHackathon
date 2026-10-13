"""Landed cost for the importer (Bangladesh destination model).

Duty is assessed on CIF value (cost + insurance + freight). On top of customs
duty we model Advance Income Tax (AIT) and a flat customs-handling fee, both
applied the way Chittagong customs applies them: percentages on CIF, flat fees
in BDT minor units.

All rates are basis points; all amounts are integer minor units. Currency
mismatches raise — conversion happens upstream in the FX calculator.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import CurrencyMismatch, Money


@dataclass(frozen=True)
class LandedCostInput:
    goods_value: Money  # invoice value (negotiable currency)
    freight: Money
    insurance: Money
    duty_rate_bp: int  # HS-line customs duty rate on CIF, 0..10_000
    ait_rate_bp: int = 500  # advance income tax on CIF (default 5%)
    flat_fees: tuple[Money, ...] = ()  # e.g. port charges, in BDT


@dataclass(frozen=True)
class LandedCostResult:
    cif: Money
    duty: Money
    ait: Money
    fees_total: Money
    landed_total: Money  # CIF + duty + AIT + fees, converted goods at stated rate


def _require_bdt(*amounts: Money) -> None:
    for a in amounts:
        if a.currency != "BDT":
            raise CurrencyMismatch(f"expected BDT, got {a.currency}")


def landed_cost_bdt(inp: LandedCostInput) -> LandedCostResult:
    """Compute landed cost. All inputs must already be in BDT (converted via FX
    at the declared customs rate upstream)."""
    _require_bdt(inp.goods_value, inp.freight, inp.insurance, *inp.flat_fees)
    for rate in (inp.duty_rate_bp, inp.ait_rate_bp):
        if not 0 <= rate <= 10_000:
            raise ValueError(f"rate out of range: {rate}")
    for a in (inp.goods_value, inp.freight, inp.insurance):
        if a.minor < 0:
            raise ValueError("amounts must be non-negative")

    cif = inp.goods_value + inp.freight + inp.insurance
    duty = cif.rate(inp.duty_rate_bp, 10_000)
    ait = cif.rate(inp.ait_rate_bp, 10_000)
    fees_total = Money.zero("BDT")
    for f in inp.flat_fees:
        fees_total = fees_total + f

    landed_total = cif + duty + ait + fees_total
    return LandedCostResult(
        cif=cif, duty=duty, ait=ait, fees_total=fees_total, landed_total=landed_total
    )
