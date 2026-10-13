"""Finance offer calculator tests."""

import pytest
from app.calc.finance import FinanceOfferInput, compare_offers, finance_offer
from app.calc.money import Money
from hypothesis import given
from hypothesis import strategies as st


def usd(minor: int) -> Money:
    return Money(minor=minor, currency="USD")


class TestReferenceCases:
    def test_standard_offer(self):
        # face 100,000.00 USD, 90 days, 90% advance, 6.5% annual, fee 250.00
        inp = FinanceOfferInput(
            face=usd(10_000_000),
            days_to_maturity=90,
            advance_rate_bp=9000,
            annual_rate_bp=650,
            flat_fee=usd(25_000),
        )
        r = finance_offer(inp)
        assert r.advance == usd(9_000_000)
        # interest = 9,000,000 * 650 * 90 / (10_000 * 360) = 146,250 minor
        assert r.interest == usd(146_250)
        assert r.net_proceeds == usd(9_000_000 - 146_250 - 25_000)
        # effective annual: (146250+25000)/8,828,750 * 360/90 * 10000 = 775.79 -> half-up 776
        total = 171_250
        expected = (total * 360 * 10_000 + (8_828_750 * 90) // 2) // (8_828_750 * 90)
        assert r.effective_cost_bp_annual == expected == 776

    def test_100pct_advance_zero_rate(self):
        inp = FinanceOfferInput(
            face=usd(1_000_000),
            days_to_maturity=30,
            advance_rate_bp=10_000,
            annual_rate_bp=0,
            flat_fee=usd(0),
        )
        r = finance_offer(inp)
        assert r.advance == r.net_proceeds == usd(1_000_000)
        assert r.effective_cost_bp_annual == 0

    def test_interest_rounds_half_up(self):
        # 1 minor advance, odd rate/days to force a fraction
        inp = FinanceOfferInput(
            face=usd(100),
            days_to_maturity=7,
            advance_rate_bp=10_000,
            annual_rate_bp=1234,
            flat_fee=usd(0),
        )
        # interest = 100 * 1234 * 7 / 3_600_000 = 863800/3600000 = 0.23994... -> 0
        r = finance_offer(inp)
        assert r.interest == usd(0)

    def test_compare_picks_highest_net(self):
        a = finance_offer(FinanceOfferInput(usd(1_000_000), 90, 8000, 800, usd(1_000)))
        b = finance_offer(FinanceOfferInput(usd(1_000_000), 90, 9500, 800, usd(1_000)))
        assert compare_offers([a, b]) is b
        assert compare_offers([]) is None

    def test_net_exactly_zero_gives_zero_effective_cost(self):
        # advance 1,000 minor (10% of 10,000), fee 1,000, no interest -> net exactly 0
        inp = FinanceOfferInput(
            face=usd(10_000),
            days_to_maturity=30,
            advance_rate_bp=1_000,
            annual_rate_bp=0,
            flat_fee=usd(1_000),
        )
        r = finance_offer(inp)
        assert r.net_proceeds == usd(0)
        assert r.effective_cost_bp_annual == 0


class TestValidation:
    @pytest.mark.parametrize(
        "kwargs, match",
        [
            ({"face": usd(0)}, "positive"),
            ({"days_to_maturity": 0}, "out of range"),
            ({"days_to_maturity": 721}, "out of range"),
            ({"advance_rate_bp": 10_001}, "out of range"),
            ({"flat_fee": Money(minor=1, currency="CNY")}, "face currency"),
            ({"flat_fee": usd(-1)}, "non-negative"),
        ],
    )
    def test_invalid(self, kwargs, match):
        base = {
            "face": usd(1_000_000),
            "days_to_maturity": 60,
            "advance_rate_bp": 9000,
            "annual_rate_bp": 600,
            "flat_fee": usd(0),
        }
        base.update(kwargs)
        with pytest.raises(ValueError, match=match):
            finance_offer(FinanceOfferInput(**base))

    def test_negative_net_rejected(self):
        # fee larger than advance
        with pytest.raises(ValueError, match="net proceeds negative"):
            finance_offer(FinanceOfferInput(usd(1_000), 30, 1_000, 0, usd(1_000)))


@given(
    face=st.integers(min_value=1, max_value=10**10),
    days=st.integers(min_value=1, max_value=720),
    adv=st.integers(min_value=0, max_value=10_000),
    rate=st.integers(min_value=0, max_value=5_000),
)
def test_net_proceeds_never_negative_and_le_advance(face: int, days: int, adv: int, rate: int):
    fee = min((face * adv) // 100_000, 10**6)
    try:
        r = finance_offer(FinanceOfferInput(usd(face), days, adv, rate, usd(fee)))
    except ValueError as e:
        assert "net proceeds negative" in str(e)
        return
    assert 0 <= r.net_proceeds.minor <= face
    assert r.advance.minor <= face
