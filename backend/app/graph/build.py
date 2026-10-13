"""Graph assembly (BUILD_PLAN §5). Wiring is code; routing is pure functions.

Model per node (plan §5):
  extract_doc, fx, cashflow, injection_screen-classifier -> fast
  plan, compliance, verify, resolve_exception            -> reasoner
  credit_offer, policy_check, execute, report            -> no LLM
  (report summary text may use fast)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import (
    approval,
    cashflow,
    compliance,
    credit_offer,
    extract_doc,
    fx,
    injection_screen,
    intake,
    plan,
    resolve,
    verify,
)
from app.graph.routers import (
    after_approval,
    after_policy,
    after_screen,
    after_verify,
    fan_out_docs,
)
from app.graph.state import DealState
from app.harness.hooks import NodeContext, wrap_with_hooks

NODES = {
    "intake": intake.intake,
    "extract_doc": extract_doc.extract_doc,
    "injection_screen": injection_screen.injection_screen,
    "plan": plan.plan,
    "compliance": compliance.compliance,
    "fx": fx.fx,
    "cashflow": cashflow.cashflow,
    "verify": verify.verify,
    "resolve_exception": resolve.resolve_exception,
    "await_corrected_doc": resolve.await_corrected_doc,
    "credit_offer": credit_offer.credit_offer,
    "policy_check": approval.policy_check,
    "human_approval": approval.human_approval,
    "execute": approval.execute,
    "escalate": approval.escalate,
    "report": approval.report,
}


def build_graph(ctx: NodeContext, checkpointer: object | None = None) -> CompiledStateGraph:  # type: ignore[type-arg]
    g = StateGraph(DealState)
    for name, fn in NODES.items():
        g.add_node(name, wrap_with_hooks(name, fn, ctx))  # type: ignore[call-overload]

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out_docs, ["extract_doc"])
    g.add_edge("extract_doc", "injection_screen")
    g.add_conditional_edges("injection_screen", after_screen, ["plan", "escalate"])
    for b in ("compliance", "fx", "cashflow"):
        g.add_edge("plan", b)
    g.add_edge(["compliance", "fx", "cashflow"], "verify")
    g.add_conditional_edges(
        "verify", after_verify, ["credit_offer", "resolve_exception", "escalate"]
    )
    g.add_edge("resolve_exception", "await_corrected_doc")
    g.add_conditional_edges("await_corrected_doc", fan_out_docs, ["extract_doc"])
    g.add_edge("credit_offer", "policy_check")
    g.add_conditional_edges("policy_check", after_policy, ["human_approval", "escalate"])
    g.add_conditional_edges("human_approval", after_approval, ["execute", "report"])
    g.add_edge("execute", "report")
    g.add_edge("escalate", "report")
    g.add_edge("report", END)

    return g.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
