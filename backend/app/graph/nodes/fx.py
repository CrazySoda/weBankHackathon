"""fx node: rank FX routes for repatriating the export proceeds.

Quotes are synthetic and labelled synthetic (rule 0.10); ranking is the pure
`rank_routes` calculator. The LLM is not involved.
"""

from __future__ import annotations

from typing import Any

from app.calc.fx import FxQuote, rank_routes
from app.calc.money import Money
from app.graph.state import DealState, FxOption
from app.harness.hooks import NodeContext

# deterministic synthetic quote book (labelled synthetic; would be a pricing
# API in production). Rates are scaled by 1e6.
SEED_QUOTE_BOOK = {
    "wire-usd-hk": FxQuote(
        route_id="wire-usd-hk",
        sell_currency="USD",
        buy_currency="CNY",
        mid_rate_scaled=7_188_000,
        spread_bp=35,
        fee=Money(minor=150_00, currency="CNY"),
        provider="synthetic:wire-hk",
    ),
    "cny-direct": FxQuote(
        route_id="cny-direct",
        sell_currency="USD",
        buy_currency="CNY",
        mid_rate_scaled=7_150_000,
        spread_bp=10,
        fee=Money(minor=5_000, currency="CNY"),
        provider="synthetic:cny-direct",
    ),
    "forward-lock": FxQuote(
        route_id="forward-lock",
        sell_currency="USD",
        buy_currency="CNY",
        mid_rate_scaled=7_170_000,
        spread_bp=20,
        fee=Money(minor=10_000, currency="CNY"),
        provider="synthetic:forward",
    ),
}


def _invoice_minor(state: DealState) -> int | None:
    for d in state.current_extracted:
        if d.kind == "commercial_invoice":
            f = d.get("total_amount")
            if f is None:
                continue
            from decimal import Decimal, InvalidOperation

            try:
                return int((Decimal(str(f.value).replace(",", "")) * 100).quantize(Decimal(1)))
            except InvalidOperation:
                continue
    return None


def fx(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    amount_minor = _invoice_minor(state)
    if amount_minor is None or amount_minor <= 0:
        return {}  # nothing to convert; not an error — deal may lack invoice yet
    amount = Money(minor=amount_minor, currency="USD")
    ranked = rank_routes(amount, list(SEED_QUOTE_BOOK.values()))
    options = [
        FxOption(
            route_id=r.quote.route_id,
            provider=r.quote.provider,
            synthetic=r.quote.synthetic,
            sell_currency=r.quote.sell_currency,
            buy_currency=r.quote.buy_currency,
            amount_minor=amount_minor,
            net_minor=r.net.minor,
            effective_rate_scaled=r.effective_rate_scaled,
            spread_bp=r.quote.spread_bp,
            fee_minor=r.quote.fee.minor,
        )
        for r in ranked
    ]
    return {"fx_options": options}
