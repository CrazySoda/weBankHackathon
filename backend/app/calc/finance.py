"""Trade-finance offer calculator (export receivables discounting model).

The seller can discount the LC receivable to get cash at shipment instead of at
maturity. Deterministic terms:

    advance      = face * advance_rate_bp / 10_000        (capped at face)
    interest     = advance * annual_rate_bp * days / (10_000 * 360)   (half-up)
    net_proceeds = advance - interest - flat_fee

`cost_of_funds_bp_annualised` restates the total cost as an annualised rate on
the *net* proceeds so offers from different providers are comparable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import Money

DAYS_IN_YEAR = 360


def _half_up_div(numerator: int, denominator: int) -> int:
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    q, r = divmod(abs(numerator), abs(denominator))
    if 2 * r >= abs(denominator):
        q += 1
    return sign * q


@dataclass(frozen=True)
class FinanceOfferInput:
    face: Money  # receivable face value (e.g. USD minor)
    days_to_maturity: int  # days from advance date to receivable maturity
    advance_rate_bp: int  # % of face advanced, 0..10_000
    annual_rate_bp: int  # financing rate, annual, on advance
    flat_fee: Money  # in face currency


@dataclass(frozen=True)
class FinanceOfferResult:
    advance: Money
    interest: Money
    fee: Money
    net_proceeds: Money
    effective_cost_bp_annual: int  # total cost / net proceeds, annualised
    total_cost: Money


def finance_offer(inp: FinanceOfferInput) -> FinanceOfferResult:
    if inp.face.minor <= 0:
        raise ValueError("face must be positive")
    if not 0 < inp.days_to_maturity <= 720:
        raise ValueError(f"days_to_maturity out of range: {inp.days_to_maturity}")
    if not 0 <= inp.advance_rate_bp <= 10_000:
        raise ValueError(f"advance_rate_bp out of range: {inp.advance_rate_bp}")
    if inp.flat_fee.currency != inp.face.currency:
        raise ValueError("flat fee must be in the face currency")
    if inp.flat_fee.minor < 0:
        raise ValueError("flat fee must be non-negative")

    advance = inp.face.rate(inp.advance_rate_bp, 10_000)
    interest_minor = _half_up_div(
        advance.minor * inp.annual_rate_bp * inp.days_to_maturity,
        10_000 * DAYS_IN_YEAR,
    )
    interest = Money(minor=interest_minor, currency=inp.face.currency)

    total_cost_minor = interest.minor + inp.flat_fee.minor
    net_minor = advance.minor - total_cost_minor
    if net_minor < 0:
        raise ValueError("offer terms consume more than the advance (net proceeds negative)")

    total_cost = Money(minor=total_cost_minor, currency=inp.face.currency)
    # annualised: cost/net * 360/days * 10_000 bp, computed on scaled ints
    effective_bp = (
        _half_up_div(total_cost_minor * DAYS_IN_YEAR * 10_000, net_minor * inp.days_to_maturity)
        if net_minor > 0
        else 0
    )

    return FinanceOfferResult(
        advance=advance,
        interest=interest,
        fee=inp.flat_fee,
        net_proceeds=Money(minor=net_minor, currency=inp.face.currency),
        effective_cost_bp_annual=effective_bp,
        total_cost=total_cost,
    )


def compare_offers(offers: list[FinanceOfferResult]) -> FinanceOfferResult | None:
    """Best offer = highest net proceeds; deterministic tie-break on cost."""
    if not offers:
        return None
    return sorted(offers, key=lambda o: (-o.net_proceeds.minor, o.effective_cost_bp_annual))[0]
