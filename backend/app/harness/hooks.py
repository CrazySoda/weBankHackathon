"""Node hooks (BUILD_PLAN §3.4).

Every graph node is wrapped: before (budget check, step count, `node_started`
audit), after (state-update validation, `node_finished` audit). Nodes never
write audit events themselves (rule 0.7) and never see budget code.

Failure semantics: any exception inside a node is converted into a
`fatal_error` state update — routers check that field first and route to
`escalate` (rule 0.6, fail closed). The wrapper never lets an exception escape
into the graph runtime.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.audit.events import AuditEvent, AuditSink
from app.graph.state import DealState
from app.harness.budget import BudgetExceeded, DealBudget

# state fields a node may not touch from inside node code
FORBIDDEN_UPDATE_FIELDS = frozenset({"deal_id", "tenant_id"})

# langgraph control-flow exception; imported defensively so the harness stays
# usable without langgraph (pure unit tests)
try:
    from langgraph.errors import GraphInterrupt as GraphInterruptError
except ImportError:  # pragma: no cover

    class GraphInterruptError(Exception):  # type: ignore[no-redef]
        pass


@dataclass
class NodeContext:
    """Shared dependencies every node receives (bound at wrap time)."""

    budget: DealBudget
    audit: AuditSink
    tools: Any = None  # ToolRegistry (avoids a cycle at import time)
    llm: Any = None  # LLMClient
    docs: Any = None  # DocumentStore
    redis: Any = None  # redis client (idempotency keys)
    anchor: Any = None  # AnchorClient


NodeFn = Callable[[DealState, NodeContext], dict[str, Any] | Any]
WrappedFn = Callable[[DealState], Any]


def _validate_update(name: str, update: dict[str, Any]) -> dict[str, Any]:
    """Reject forbidden fields; drop None for reducer-managed list fields."""
    bad = FORBIDDEN_UPDATE_FIELDS & set(update)
    if bad:
        raise ValueError(f"node {name} attempted to modify protected fields: {sorted(bad)}")
    return update


def _summary(update: dict[str, Any]) -> dict[str, Any]:
    """Small, safe digest of an update for the audit trail (no raw doc text)."""
    out: dict[str, Any] = {"keys": sorted(update.keys())}
    if "findings" in update:
        fs = update["findings"]
        out["findings"] = [
            {"check_id": f.check_id, "rule_id": f.rule_id, "severity": f.severity} for f in fs
        ]
    if "injection_flags" in update:
        out["injection_flags"] = len(update["injection_flags"])
    return out


def wrap_with_hooks(name: str, fn: NodeFn, ctx: NodeContext) -> WrappedFn:
    async def wrapped(state: DealState | dict[str, Any]) -> dict[str, Any]:
        # Send() args arrive as partial dicts; coerce to the state model
        if not isinstance(state, DealState):
            state = DealState.model_validate(state)
        # -- before --
        try:
            ctx.budget.check_step()
            ctx.budget.record_step()
            ctx.audit.emit(
                AuditEvent(
                    kind="node_started",
                    deal_id=state.deal_id,
                    tenant_id=state.tenant_id,
                    payload={"node": name, "step": ctx.budget.steps},
                )
            )
        except BudgetExceeded as e:
            ctx.audit.emit(
                AuditEvent(
                    kind="budget_exceeded",
                    deal_id=state.deal_id,
                    tenant_id=state.tenant_id,
                    payload={"node": name, "reason": e.reason},
                )
            )
            return {"fatal_error": f"budget: {e.reason}"}

        # -- node --
        try:
            outcome = fn(state, ctx)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            update = _validate_update(name, outcome)
        except GraphInterruptError as interrupt_exc:
            # control-flow exception from langgraph interrupt(): must propagate,
            # not be turned into a failure
            ctx.audit.emit(
                AuditEvent(
                    kind="node_interrupted",
                    deal_id=state.deal_id,
                    tenant_id=state.tenant_id,
                    payload={"node": name},
                )
            )
            raise interrupt_exc from None
        except Exception as e:
            ctx.audit.emit(
                AuditEvent(
                    kind="node_failed",
                    deal_id=state.deal_id,
                    tenant_id=state.tenant_id,
                    payload={"node": name, "error": repr(e)},
                )
            )
            return {"fatal_error": f"node {name} failed: {e}"}

        # -- after --
        try:
            ctx.audit.emit(
                AuditEvent(
                    kind="node_finished",
                    deal_id=state.deal_id,
                    tenant_id=state.tenant_id,
                    payload={"node": name, "summary": _summary(update)},
                )
            )
        except ValidationError:
            return {"fatal_error": f"node {name}: audit write failed"}
        return update

    wrapped.__name__ = name
    wrapped.__qualname__ = f"wrapped_{name}"
    return wrapped


def validate_state_invariants(state: DealState) -> list[str]:
    """Post-node state checks the `after` hook can run (cheap, pure).
    Returns a list of invariant violations (empty = healthy)."""
    problems: list[str] = []
    for doc in state.extracted:
        for field in doc.fields:
            if not 0.0 <= field.confidence <= 1.0:
                problems.append(f"confidence out of range in {doc.sha256}:{field.name}")
    if state.cash_projection and len(state.cash_projection.daily_balance_minor) == 0:
        problems.append("empty cash projection")
    if state.receipt is not None and state.approval is None:
        problems.append("receipt without approval")
    return problems
