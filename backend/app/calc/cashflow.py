"""90-day cash projection with what-if inputs.

The projection is a list of dated events (day offset from deal date, signed
amount, currency). The calculator folds events into a daily balance series and
reports the minimum balance, the number of days below zero, and the day of the
deepest gap. What-if inputs (e.g. a finance advance on day N) are simply extra
events — the same function prices every scenario, so comparing scenarios is a
pure diff of outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import Money

HORIZON_DAYS = 90


@dataclass(frozen=True)
class CashEvent:
    day: int  # 0..HORIZON_DAYS, day 0 = deal date
    amount: Money  # positive = inflow, negative = outflow
    label: str
    source: str = "deal"  # deal | what_if | finance


@dataclass(frozen=True)
class CashProjection:
    currency: str
    opening_balance: Money
    daily_balance: list[Money]  # length HORIZON_DAYS + 1, balance at end of day d
    min_balance: Money
    min_balance_day: int
    days_below_zero: int
    inflows: Money
    outflows: Money  # negative minor


def project_cash_flow(
    events: list[CashEvent],
    currency: str,
    opening_balance: Money | None = None,
) -> CashProjection:
    for e in events:
        if e.amount.currency != currency:
            raise ValueError(f"event {e.label!r} is {e.amount.currency}, expected {currency}")
        if not 0 <= e.day <= HORIZON_DAYS:
            raise ValueError(f"event day {e.day} outside 0..{HORIZON_DAYS}")

    opening = opening_balance if opening_balance is not None else Money.zero(currency)
    if opening.currency != currency:
        raise ValueError(f"opening balance is {opening.currency}, expected {currency}")

    daily: list[Money] = []
    by_day: dict[int, int] = {}
    inflow = 0
    outflow = 0
    for e in events:
        by_day[e.day] = by_day.get(e.day, 0) + e.amount.minor
        if e.amount.minor >= 0:
            inflow += e.amount.minor
        else:
            outflow += e.amount.minor

    running = opening.minor
    for day in range(HORIZON_DAYS + 1):
        running += by_day.get(day, 0)
        daily.append(Money(minor=running, currency=currency))

    min_balance = min(daily)
    min_day = daily.index(min_balance)
    below = sum(1 for b in daily if b.minor < 0)

    return CashProjection(
        currency=currency,
        opening_balance=opening,
        daily_balance=daily,
        min_balance=min_balance,
        min_balance_day=min_day,
        days_below_zero=below,
        inflows=Money(minor=inflow, currency=currency),
        outflows=Money(minor=outflow, currency=currency),
    )
