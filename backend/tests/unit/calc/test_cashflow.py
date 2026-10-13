"""90-day cash projection tests."""

import pytest
from app.calc.cashflow import HORIZON_DAYS, CashEvent, project_cash_flow
from app.calc.money import Money
from hypothesis import given
from hypothesis import strategies as st


def usd(minor: int) -> Money:
    return Money(minor=minor, currency="USD")


def ev(day: int, minor: int, label: str = "e") -> CashEvent:
    return CashEvent(day=day, amount=usd(minor), label=label)


class TestReferenceCases:
    def test_simple_ship_now_pay_later_gap(self):
        # deposit outflow day 0, LC receipt day 60
        events = [ev(0, -500_000_00, "deposit"), ev(60, 1_000_000_00, "lc")]
        p = project_cash_flow(events, "USD")
        assert len(p.daily_balance) == HORIZON_DAYS + 1
        assert p.daily_balance[0] == usd(-500_000_00)
        assert p.daily_balance[59] == usd(-500_000_00)
        assert p.daily_balance[60] == usd(500_000_00)
        assert p.min_balance == usd(-500_000_00)
        assert p.min_balance_day == 0
        assert p.days_below_zero == 60  # days 0..59
        assert p.inflows == usd(100_000_000)
        assert p.outflows == usd(-50_000_000)

    def test_opening_balance_counts(self):
        p = project_cash_flow([ev(10, -100)], "USD", opening_balance=usd(500))
        assert p.daily_balance[9] == usd(500)
        assert p.daily_balance[10] == usd(400)
        assert p.days_below_zero == 0

    def test_what_if_advance_shrinks_gap(self):
        base = [ev(0, -500_000_00), ev(60, 1_000_000_00)]
        advance = lambda minor: CashEvent(  # noqa: E731 - test helper
            day=5, amount=usd(minor), label="advance", source="finance"
        )
        partial = [*base, advance(450_000_00)]
        full = [*base, advance(500_000_00)]
        p0 = project_cash_flow(base, "USD")
        p1 = project_cash_flow(partial, "USD")
        p2 = project_cash_flow(full, "USD")
        assert p0.days_below_zero == 60
        # partial advance shrinks the gap after day 5 but the deepest point is still day 0
        assert p1.days_below_zero == 60
        assert p1.daily_balance[5] == usd(-50_000_00)
        assert p1.min_balance == usd(-500_000_00)
        assert p1.min_balance_day == 0
        # full advance at day 5: days 0..4 still deep negative, day 5 onward >= 0
        assert p2.days_below_zero == 5
        assert p2.daily_balance[5].minor == 0


class TestValidation:
    def test_day_out_of_range(self):
        with pytest.raises(ValueError, match="outside"):
            project_cash_flow([ev(HORIZON_DAYS + 1, 1)], "USD")

    def test_currency_mismatch(self):
        with pytest.raises(ValueError, match="expected USD"):
            project_cash_flow(
                [CashEvent(day=0, amount=Money(minor=1, currency="CNY"), label="x")], "USD"
            )

    def test_opening_currency(self):
        with pytest.raises(ValueError, match="opening balance"):
            project_cash_flow([], "USD", opening_balance=Money(minor=1, currency="CNY"))

    def test_empty_projection_is_valid(self):
        p = project_cash_flow([], "USD")
        assert p.daily_balance[-1] == usd(0)
        assert p.days_below_zero == 0


@given(
    events=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=HORIZON_DAYS),
            st.integers(min_value=-(10**8), max_value=10**8),
        ),
        max_size=20,
    ),
    opening=st.integers(min_value=-(10**8), max_value=10**8),
)
def test_balance_series_sum_invariant(events: list[tuple[int, int]], opening: int):
    """Final balance equals opening + sum of all events, regardless of ordering."""
    evs = [CashEvent(day=d, amount=usd(m), label=f"e{i}") for i, (d, m) in enumerate(events)]
    p = project_cash_flow(evs, "USD", opening_balance=usd(opening))
    expected_final = opening + sum(m for _, m in events)
    assert p.daily_balance[-1].minor == expected_final
