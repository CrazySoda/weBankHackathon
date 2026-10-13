"""resolve_exception + await_corrected_doc nodes.

resolve_exception drafts an amendment message (text only — never sends) and
bumps the retry counter. await_corrected_doc interrupts the graph; the operator
attaches a corrected document and the fan-out router re-extracts it.
Max 1 retry: the after_verify router escalates on the second failure.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.graph.state import DealState
from app.harness.hooks import NodeContext


class AmendmentDraft(BaseModel):
    subject: str
    body: str


async def resolve_exception(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    assert ctx.llm is not None
    fixable = [
        f for f in state.findings if f.severity == "block" and f.fixable and f.status == "open"
    ]
    if not fixable:
        return {"resolve_attempts": state.resolve_attempts + 1}

    system, version = ctx.system_prompt("resolve_exception", state)
    result = await ctx.llm.complete(
        alias="reasoner",
        system=system + "\n\n" + (
            "Draft an amendment request to the buyer/applicant that fixes the listed "
            "document discrepancies. Quote the exact correction needed for each. "
            "Text only — you cannot send anything."
        ),
        messages=[
            {
                "role": "user",
                "content": "<untrusted>\n"
                + "\n".join(f"- [{f.rule_id}] {f.summary}" for f in fixable)
                + "\n</untrusted>",
            }
        ],
        output_model=AmendmentDraft,
        node="resolve_exception",
        prompt_version=version,
    )
    draft = f"{result.output.subject}\n\n{result.output.body}"
    return {"amendment_draft": draft, "resolve_attempts": state.resolve_attempts + 1,
            "served_by": [result.use]}


async def await_corrected_doc(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    """Interrupt point. LangGraph's interrupt() parks the graph; on resume with
    a corrected document the fan-out router re-runs extraction."""
    from langgraph.types import interrupt

    payload = {
        "kind": "await_corrected_doc",
        "amendment_draft": state.amendment_draft,
        "open_block_findings": [
            {"rule_id": f.rule_id, "summary": f.summary}
            for f in state.findings
            if f.severity == "block" and f.status == "open"
        ],
    }
    resume = interrupt(payload)
    if not isinstance(resume, dict) or resume.get("action") != "corrected_document":
        return {"fatal_error": "corrected-document interrupt resumed without a corrected upload"}
    docs = resume.get("documents")
    if not isinstance(docs, list) or not docs:
        return {"fatal_error": "corrected-document resume is missing document references"}
    return {"documents": docs}
