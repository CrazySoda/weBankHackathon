"""plan node: `reasoner` picks which skills/checks this deal needs.

The plan constrains which skills the loader injects into downstream prompts
(progressive loading, M4). The router still decides control flow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.graph.state import CheckPlan, DealState, new_id
from app.harness.hooks import NodeContext

# curated catalogue (mirrors skills/ dir; loader validates against SKILL.md)
AVAILABLE_SKILLS = [
    "lc-ucp600-check",
    "bd-import-docs",
    "cn-export-vat-refund",
    "hs-classification",
    "sanctions-screening",
    "fx-route-compare",
    "cashflow-gap",
    "amendment-drafting",
    "explain-for-sme",
]

DEFAULT_CHECKS = [
    "lc-consistency",
    "sanctions-screen",
    "vat-refund",
    "fx-compare",
    "cash-gap",
]


class PlanOutput(BaseModel):
    chosen_skills: list[str] = Field(default_factory=list)
    rationale: str = ""


def _validate_skills(chosen: list[str]) -> list[str]:
    known = set(AVAILABLE_SKILLS)
    return [s for s in chosen if s in known]  # drop hallucinated skills


async def plan(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    assert ctx.llm is not None
    doc_kinds = sorted({d.kind for d in state.extracted})
    system, version = ctx.system_prompt(
        "plan", state, "Choose only catalogue skills. The router controls all transitions."
    )
    result = await ctx.llm.complete(
        alias="reasoner",
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Documents: {doc_kinds}\n"
                    f"Open injection flags: {len(state.injection_flags)}\n"
                    f"Catalogue: {AVAILABLE_SKILLS}\n"
                    "Return the chosen skills and a short rationale."
                ),
            }
        ],
        output_model=PlanOutput,
        node="plan",
        prompt_version=version,
    )
    # The model may recommend skills, but cannot suppress required checks.
    chosen = _validate_skills(result.output.chosen_skills)
    required = {
        "lc-ucp600-check", "bd-import-docs", "cn-export-vat-refund",
        "hs-classification", "sanctions-screening", "explain-for-sme",
        "amendment-drafting",
    }
    kinds = {d.kind for d in state.extracted}
    if "commercial_invoice" in kinds:
        required.update({"fx-route-compare", "cashflow-gap"})
    if any(f.severity == "block" and f.fixable for f in state.findings):
        required.add("amendment-drafting")
    chosen = sorted(set(chosen) | required)
    checks = list(DEFAULT_CHECKS)
    return {
        "served_by": [result.use],
        "check_plan": CheckPlan(
            plan_id=new_id("plan"),
            chosen_skills=chosen,
            checks=checks,
            rationale=result.output.rationale[:500],
        )
    }
