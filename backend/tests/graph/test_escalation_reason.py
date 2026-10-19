"""The operator is told why a deal escalated: an unscreenable image is not 'an injection'."""

from __future__ import annotations

from app.graph.nodes.approval import escalate
from app.graph.nodes.injection_screen import UNSCREENABLE_DETAIL
from app.graph.state import DealState, Flag


def flag(detail: str) -> Flag:
    return Flag(kind="classifier_hit", severity="block", doc_id="d1", detail=detail)  # type: ignore[call-arg]


async def reason_for(flags: list[Flag], ctx) -> str:
    state = DealState(deal_id="d1", tenant_id="t1", injection_flags=flags)
    return (await escalate(state, ctx))["escalation_reason"]


class TestEscalationReason:
    async def test_unscreenable_image_is_not_called_an_injection(self, ctx):
        reason = await reason_for([flag(UNSCREENABLE_DETAIL)], ctx)
        assert "cannot be screened" in reason
        assert "injection" not in reason

    async def test_a_real_injection_flag_still_says_so(self, ctx):
        assert await reason_for([flag("hidden text found")], ctx) == (
            "prompt injection detected in documents"
        )

    async def test_a_real_flag_next_to_an_image_still_says_injection(self, ctx):
        reason = await reason_for([flag(UNSCREENABLE_DETAIL), flag("hidden text found")], ctx)
        assert reason == "prompt injection detected in documents"
