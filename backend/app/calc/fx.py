"""FX route comparison.

Each route quotes: a mid rate (as integer "price units per base unit" scaled by
RATE_SCALE), a spread in basis points charged on the converted amount, and a
fixed fee in the target currency. The effective conversion is:

    converted = amount * mid / RATE_SCALE, rounded half-up
    net       = converted - spread(converted) - fee

All rates use integer arithmetic: `RATE_SCALE` divides the quoted rate (a rate
of 7_188_000 / 1_000_000 = 7.188 CNY per USD). Rounding is always half-up and
stated, never implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import Money

RATE_SCALE = 1_000_000


@dataclass(frozen=True)
class FxQuote:
    route_id: str  # e.g. "wire-usd-hk", "cny-direct", "header-hedge"
    sell_currency: str
    buy_currency: str
    mid_rate_scaled: int  # buy units per sell unit, scaled by RATE_SCALE
    spread_bp: int  # spread charged on the converted amount, 0..10_000
    fee: Money  # fixed fee in the *buy* currency
    provider: str
    synthetic: bool = True  # demo quotes are always labelled synthetic


@dataclass(frozen=True)
class FxRouteResult:
    quote: FxQuote
    converted_gross: Money
    spread_amount: Money
    fee: Money
    net: Money  # what actually arrives
    effective_rate_scaled: int  # net per 1 sell unit, scaled by RATE_SCALE


def _half_up_div(numerator: int, denominator: int) -> int:
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    q, r = divmod(abs(numerator), abs(denominator))
    if 2 * r >= abs(denominator):
        q += 1
    return sign * q


def effective_fx_cost(amount: Money, quote: FxQuote) -> FxRouteResult:
    if amount.currency != quote.sell_currency:
        raise ValueError(
            f"amount currency {amount.currency} != quote sell currency {quote.sell_currency}"
        )
    if amount.minor < 0:
        raise ValueError("amount must be non-negative")
    if amount.minor == 0 and quote.fee.minor > 0:
        raise ValueError("zero-amount conversion with a fee is a caller error")
    if not 0 <= quote.spread_bp <= 10_000:
        raise ValueError(f"spread_bp out of range: {quote.spread_bp}")
    if quote.fee.currency != quote.buy_currency:
        raise ValueError("fee must be denominated in the buy currency")

    gross_minor = _half_up_div(amount.minor * quote.mid_rate_scaled, RATE_SCALE)
    gross = Money(minor=gross_minor, currency=quote.buy_currency)

    spread_amount = gross.rate(quote.spread_bp, 10_000)
    net_minor = gross.minor - spread_amount.minor - quote.fee.minor
    net = Money(minor=net_minor, currency=quote.buy_currency)

    effective = _half_up_div(net.minor * RATE_SCALE, amount.minor) if amount.minor else 0
    return FxRouteResult(
        quote=quote,
        converted_gross=gross,
        spread_amount=spread_amount,
        fee=quote.fee,
        net=net,
        effective_rate_scaled=effective,
    )


def rank_routes(amount: Money, quotes: list[FxQuote]) -> list[FxRouteResult]:
    """Routes ranked best-first by net proceeds. Pure: same input, same order
    (ties broken deterministically by route_id)."""
    if not quotes:
        raise ValueError("at least one quote is required")
    results = [effective_fx_cost(amount, q) for q in quotes]
    results.sort(key=lambda r: (-r.net.minor, r.quote.route_id))
    return results
