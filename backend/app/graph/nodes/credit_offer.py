"""credit_offer node: trade-finance offer via the pure calculator.

No LLM (plan §5): terms come from the seeded provider table, math from
`app.calc.finance`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.calc.finance import FinanceOfferInput, finance_offer
from app.calc.money import Money
from app.graph.state import DealState, FinanceOfferState
from app.harness.hooks import NodeContext

DEFAULT_TENOR = 60

# synthetic provider terms (labelled synthetic); would be a lender API in prod
PROVIDER_TERMS = [
    # (provider, advance_rate_bp, annual_rate_bp, flat fee USD minor)
    ("synthetic:global-factor", 9000, 650, 25_000),
    ("synthetic:sz-trade-fin", 9500, 780, 10_000),
    ("synthetic:hk-discount", 8500, 520, 40_000),
]


def _lc_amount(state: DealState) -> int | None:
    for d in state.extracted:
        if d.kind == "letter_of_credit":
            f = d.get("lc_amount") or d.get("total_amount")
            if f is None:
                continue
            from decimal import Decimal, InvalidOperation

            try:
                return int((Decimal(str(f.value).replace(",", "")) * 100).quantize(Decimal(1)))
            except InvalidOperation:
                continue
    return None


def credit_offer(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    minor = _lc_amount(state)
    if minor is None or minor <= 0:
        return {}
    face = Money(minor=minor, currency="USD")
    tenor = DEFAULT_TENOR
    for d in state.extracted:
        t = d.get("lc_tenor_days")
        if t is not None:
            with contextlib.suppress(ValueError):
                tenor = max(1, min(int(str(t.value)), 720))

    best: FinanceOfferState | None = None
    for provider, adv_bp, rate_bp, fee_minor in PROVIDER_TERMS:
        try:
            r = finance_offer(
                FinanceOfferInput(
                    face=face,
                    days_to_maturity=tenor,
                    advance_rate_bp=adv_bp,
                    annual_rate_bp=rate_bp,
                    flat_fee=Money(minor=fee_minor, currency="USD"),
                )
            )
        except ValueError:
            continue
        offer = FinanceOfferState.from_result(provider, tenor, face, r)
        if best is None or offer.net_proceeds.minor > best.net_proceeds.minor:
            best = offer

    return {"finance_offer": best} if best else {}
