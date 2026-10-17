"""cashflow node: 90-day projection from deal events (pure calculator).

Baseline events: deposit outflow at day 0, LC receipt at maturity. The FX
route choice and a finance advance are what-if overlays applied downstream by
re-running the same pure function.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.calc.cashflow import HORIZON_DAYS, CashEvent, project_cash_flow
from app.calc.money import Money
from app.graph.state import CashEventState, CashProjectionState, DealState
from app.harness.hooks import NodeContext

DEFAULT_LC_TENOR_DAYS = 60


def _deposit_and_tenor(state: DealState) -> tuple[int | None, int]:
    """(invoice minor USD, LC tenor in days)."""
    minor = None
    tenor = DEFAULT_LC_TENOR_DAYS
    for d in state.current_extracted:
        f = d.get("total_amount")
        if d.kind == "commercial_invoice" and f is not None:
            from decimal import Decimal, InvalidOperation

            with contextlib.suppress(InvalidOperation):
                minor = int((Decimal(str(f.value).replace(",", "")) * 100).quantize(Decimal(1)))
        t = d.get("lc_tenor_days")
        if t is not None:
            with contextlib.suppress(ValueError):
                tenor = max(1, min(int(str(t.value)), HORIZON_DAYS))
    return minor, tenor


def cashflow(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    minor, tenor = _deposit_and_tenor(state)
    if minor is None or minor <= 0:
        return {}
    events = [
        CashEvent(
            day=0,
            amount=Money(minor=-minor * 30 // 100, currency="USD"),
            label="production deposit (30%)",
        ),
        CashEvent(
            day=min(tenor, HORIZON_DAYS),
            amount=Money(minor=minor, currency="USD"),
            label="LC receipt at maturity",
        ),
    ]
    p = project_cash_flow(events, "USD")
    return {
        "cash_projection": CashProjectionState(
            currency="USD",
            opening_balance_minor=0,
            daily_balance_minor=[b.minor for b in p.daily_balance],
            min_balance_minor=p.min_balance.minor,
            min_balance_day=p.min_balance_day,
            days_below_zero=p.days_below_zero,
            events=[
                CashEventState(
                    day=e.day,
                    amount_minor=e.amount.minor,
                    currency="USD",
                    label=e.label,
                    source=e.source,
                )
                for e in events
            ],
        )
    }
