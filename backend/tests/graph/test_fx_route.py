"""The approver can pick an FX route; the choice is signed (DECISIONS #26)."""

from __future__ import annotations

import pytest
from app.graph.build import build_graph
from app.graph.state import DealState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from tests.graph.conftest import sign_for
from tests.graph.test_graph import extract_interrupts, extraction_for_hint, lc_and_inv


@pytest.fixture()
def graph(ctx):
    return build_graph(ctx, checkpointer=InMemorySaver())


async def _parked_at_approval(graph, fake_llm, docs_store, deal_id: str):
    fake_llm.hooks["ExtractionOutput"] = extraction_for_hint
    lc, inv = lc_and_inv(deal_id, docs_store)
    state = DealState(deal_id=deal_id, tenant_id="t1", documents=[lc, inv])
    config = {"configurable": {"thread_id": deal_id}}
    result = await graph.ainvoke(state, config=config)
    return extract_interrupts(result)[0].value, config


def _routes(render: dict) -> tuple[str, str]:
    """(best route id, a different route id)."""
    options = sorted(render["fx_options"], key=lambda o: o["net_minor"], reverse=True)
    assert len(options) >= 2
    return options[0]["route_id"], options[1]["route_id"]


def _signed_for(render: dict, route: str, key) -> dict:
    return sign_for({**render, "fx_route": route}, key)


class TestFxRouteSelection:
    async def test_default_is_the_best_route_and_is_in_the_signed_render(
        self, graph, fake_llm, docs_store, owner_key
    ):
        render, config = await _parked_at_approval(graph, fake_llm, docs_store, "fx1")
        best, _ = _routes(render)
        assert render["fx_route"] == best

        final = await graph.ainvoke(
            Command(resume={"approval": sign_for(render, owner_key)}), config=config
        )
        assert final["receipt"] is not None
        assert final.get("selected_fx_route") is None  # nothing was overridden

    async def test_a_chosen_route_signed_by_the_approver_pays_out(
        self, graph, fake_llm, docs_store, owner_key
    ):
        render, config = await _parked_at_approval(graph, fake_llm, docs_store, "fx2")
        _, other = _routes(render)

        final = await graph.ainvoke(
            Command(resume={"approval": _signed_for(render, other, owner_key), "fx_route": other}),
            config=config,
        )
        assert final["receipt"] is not None
        assert final["selected_fx_route"] == other
        assert "Approver selected FX route: " + other in final["report_summary"]

    async def test_route_changed_after_signing_is_rejected(
        self, graph, fake_llm, docs_store, owner_key
    ):
        render, config = await _parked_at_approval(graph, fake_llm, docs_store, "fx3")
        best, other = _routes(render)

        # signed for the recommended route, but the resume names a different one
        final = await graph.ainvoke(
            Command(resume={"approval": _signed_for(render, best, owner_key), "fx_route": other}),
            config=config,
        )
        assert final.get("receipt") is None
        assert "changed after signing" in (final.get("fatal_error") or "")

    async def test_signed_choice_dropped_at_resume_is_rejected(
        self, graph, fake_llm, docs_store, owner_key
    ):
        render, config = await _parked_at_approval(graph, fake_llm, docs_store, "fx4")
        _, other = _routes(render)

        # signed for a non-default route, resumed without naming it: falls back to the
        # default, which the signature does not cover
        final = await graph.ainvoke(
            Command(resume={"approval": _signed_for(render, other, owner_key)}), config=config
        )
        assert final.get("receipt") is None
        assert "changed after signing" in (final.get("fatal_error") or "")

    async def test_unknown_route_fails_closed(self, graph, fake_llm, docs_store, owner_key):
        render, config = await _parked_at_approval(graph, fake_llm, docs_store, "fx5")

        final = await graph.ainvoke(
            Command(
                resume={
                    "approval": _signed_for(render, "no-such-route", owner_key),
                    "fx_route": "no-such-route",
                }
            ),
            config=config,
        )
        assert final.get("receipt") is None
        assert "unknown FX route" in (final.get("fatal_error") or "")
