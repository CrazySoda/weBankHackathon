"""Pure routing functions (BUILD_PLAN §5, M5).

Workflow, not orchestrator (rule 0.1): these are plain deterministic functions
of state — no model ever decides the next node. Every router checks
`fatal_error` first and routes to escalate (rule 0.6, fail closed).
"""

from __future__ import annotations

from typing import Literal

from langgraph.types import Send

from app.graph.state import DealState

RouterOutcome = Literal[
    "plan", "credit_offer", "resolve_exception", "human_approval", "execute", "report", "escalate"
]


def fatal(state: DealState) -> bool:
    return state.fatal_error is not None


def fan_out_docs(state: DealState) -> list[Send]:
    """One `extract_doc` Send per document that lacks an extraction yet."""
    extracted_hashes = {d.sha256 for d in state.extracted}
    return [
        Send(
            "extract_doc",
            {
                "pending_doc": doc.model_dump(),
                "deal_id": state.deal_id,
                "tenant_id": state.tenant_id,
            },
        )
        for doc in state.documents
        if doc.sha256 not in extracted_hashes
    ]


def after_screen(state: DealState) -> RouterOutcome:
    if fatal(state) or state.blocked_by_injection():
        return "escalate"
    return "plan"


def after_verify(state: DealState) -> RouterOutcome:
    if fatal(state):
        return "escalate"
    blocks = [f for f in state.findings if f.severity == "block" and f.status == "open"]
    fixable = [f for f in blocks if f.fixable]
    if not blocks:
        return "credit_offer"
    if fixable and state.resolve_attempts < 1:
        return "resolve_exception"
    return "escalate"


def after_policy(state: DealState) -> RouterOutcome:
    if fatal(state):
        return "escalate"
    if state.policy is None:
        return "escalate"
    return "human_approval" if state.policy.decision == "allow" else "escalate"


def after_approval(state: DealState) -> RouterOutcome:
    # approval rejected/absent -> report without execution
    if state.approval is not None:
        return "execute"
    return "report"
