from __future__ import annotations

from app.graph.state import DealState, FxOption
from app.security.approval import approval_render


def option(route_id: str, net_minor: int) -> FxOption:
    return FxOption(
        route_id=route_id,
        provider=route_id,
        sell_currency="USD",
        buy_currency="CNY",
        amount_minor=100,
        net_minor=net_minor,
        effective_rate_scaled=7_000_000,
        spread_bp=10,
        fee_minor=1,
    )


def state(**kw) -> DealState:
    return DealState(
        deal_id="d1",
        tenant_id="t1",
        fx_options=[option("low", 100), option("high", 300), option("mid", 200)],
        **kw,
    )


class TestChosenFxRoute:
    def test_no_options_means_no_route(self):
        assert DealState(deal_id="d", tenant_id="t").chosen_fx_route() is None

    def test_default_is_best_net(self):
        chosen = state().chosen_fx_route()
        assert chosen is not None and chosen.route_id == "high"

    def test_selection_overrides_the_default(self):
        chosen = state(selected_fx_route="low").chosen_fx_route()
        assert chosen is not None and chosen.route_id == "low"

    def test_unknown_selection_does_not_fall_back_silently(self):
        assert state(selected_fx_route="ghost").chosen_fx_route() is None


class TestRenderCarriesTheRoute:
    def test_default_route_is_rendered(self):
        assert approval_render(state())["fx_route"] == "high"

    def test_selected_route_is_rendered(self):
        assert approval_render(state(selected_fx_route="mid"))["fx_route"] == "mid"

    def test_no_options_renders_none(self):
        assert approval_render(DealState(deal_id="d", tenant_id="t"))["fx_route"] is None
