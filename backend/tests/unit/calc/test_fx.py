"""FX route comparison: reference cases + ranking determinism."""

import pytest
from app.calc.fx import FxQuote, effective_fx_cost, rank_routes
from app.calc.money import Money
from hypothesis import given
from hypothesis import strategies as st


def usd(minor: int) -> Money:
    return Money(minor=minor, currency="USD")


def cny(minor: int) -> Money:
    return Money(minor=minor, currency="CNY")


def quote(route_id: str, mid: int, spread: int, fee_minor: int) -> FxQuote:
    return FxQuote(
        route_id=route_id,
        sell_currency="USD",
        buy_currency="CNY",
        mid_rate_scaled=mid,
        spread_bp=spread,
        fee=cny(fee_minor),
        provider="synthetic-bank",
    )


class TestReferenceCases:
    def test_basic_conversion(self):
        # 100,000.00 USD at 7.188000 CNY/USD, 0 spread, 0 fee -> 718,800.00 CNY
        r = effective_fx_cost(usd(10_000_000), quote("a", 7_188_000, 0, 0))
        assert r.converted_gross == cny(71_880_000)
        assert r.net == cny(71_880_000)
        assert r.effective_rate_scaled == 7_188_000

    def test_spread_and_fee(self):
        # gross 718,800.00 CNY; spread 30bp = 2,156.40 -> half-up 2,156.40 = 215,640 minor
        # wait: 71,880,000 minor * 30 / 10,000 = 215,640 minor = 2,156.40 CNY. Fee 150.00 CNY.
        r = effective_fx_cost(usd(10_000_000), quote("a", 7_188_000, 30, 15_000))
        assert r.converted_gross == cny(71_880_000)
        assert r.spread_amount == cny(215_640)
        assert r.net == cny(71_880_000 - 215_640 - 15_000)
        # effective rate scaled: net minor per 10,000,000 USD minor * 1e6
        expected = (71_880_000 - 215_640 - 15_000) * 1_000_000 // 10_000_000
        assert r.effective_rate_scaled == expected

    def test_zero_amount(self):
        r = effective_fx_cost(usd(0), quote("a", 7_188_000, 30, 0))
        assert r.net == cny(0)
        assert r.effective_rate_scaled == 0

    def test_zero_amount_with_fee_rejected(self):
        with pytest.raises(ValueError, match="caller error"):
            effective_fx_cost(usd(0), quote("a", 7_188_000, 30, 15_000))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            effective_fx_cost(usd(-1), quote("a", 7_188_000, 0, 0))


class TestRanking:
    def test_best_route_first(self):
        amount = usd(10_000_000)
        routes = [
            quote("wire", 7_188_000, 50, 50_000),
            quote("direct", 7_150_000, 10, 5_000),
            quote("hedge", 7_180_000, 20, 10_000),
        ]
        # wire:   718,800.00 - 3,594.00 (50bp) - 500.00 = 714,706.00
        # hedge:  718,000.00 - 1,436.00 (20bp) - 100.00 = 716,464.00
        # direct: 715,000.00 -   715.00 (10bp) -  50.00 = 714,235.00
        ranked = rank_routes(amount, routes)
        assert [r.quote.route_id for r in ranked] == ["hedge", "wire", "direct"]
        assert ranked[0].net.minor >= ranked[1].net.minor >= ranked[2].net.minor

    def test_tie_broken_by_route_id(self):
        amount = usd(1_000_000)
        a = quote("aaa", 7_000_000, 0, 0)
        b = quote("bbb", 7_000_000, 0, 0)
        ranked = rank_routes(amount, [b, a])
        assert [r.quote.route_id for r in ranked] == ["aaa", "bbb"]

    def test_empty_quotes(self):
        with pytest.raises(ValueError, match="at least one"):
            rank_routes(usd(1), [])


class TestValidation:
    def test_currency_mismatch(self):
        with pytest.raises(ValueError, match="sell currency"):
            effective_fx_cost(cny(1), quote("a", 7_000_000, 0, 0))

    def test_fee_currency(self):
        q = FxQuote(
            route_id="a",
            sell_currency="USD",
            buy_currency="CNY",
            mid_rate_scaled=7_000_000,
            spread_bp=0,
            fee=usd(1),
            provider="x",
        )
        with pytest.raises(ValueError, match="buy currency"):
            effective_fx_cost(usd(1), q)

    @pytest.mark.parametrize("spread", [-1, 10_001])
    def test_spread_bounds(self, spread: int):
        with pytest.raises(ValueError, match="out of range"):
            effective_fx_cost(usd(1), quote("a", 7_000_000, spread, 0))


@given(
    minor=st.integers(min_value=0, max_value=10**10),
    mid=st.integers(min_value=1, max_value=20_000_000),
    spread=st.integers(min_value=0, max_value=10_000),
)
def test_net_never_exceeds_gross(minor: int, mid: int, spread: int):
    r = effective_fx_cost(usd(minor), quote("a", mid, spread, 0))
    assert r.net.minor <= r.converted_gross.minor
    assert r.net.minor >= 0


@given(st.data())
def test_ranking_is_consistent(data):
    n = data.draw(st.integers(min_value=1, max_value=6))
    routes = [
        quote(
            f"r{i}",
            data.draw(st.integers(min_value=1_000_000, max_value=9_000_000)),
            data.draw(st.integers(min_value=0, max_value=200)),
            0,
        )
        for i in range(n)
    ]
    amount = usd(data.draw(st.integers(min_value=1, max_value=10**8)))
    ranked1 = rank_routes(amount, routes)
    ranked2 = rank_routes(amount, list(reversed(routes)))
    assert [r.quote.route_id for r in ranked1] == [r.quote.route_id for r in ranked2]
