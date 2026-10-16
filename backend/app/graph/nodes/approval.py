"""policy_check, human_approval, execute, escalate, report nodes.

- policy_check: evaluates the Cedar policy set (numbers fixed upstream).
- human_approval: interrupt; resume carries a SignedApproval which is verified
  against deal_hash (signature + post-sign state change checks).
- execute: idempotent sandbox payout + chain anchoring (only node allowed to).
- escalate: parks the deal with a reason.
- report: final summary; numbers come from state, text is template or `fast`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.graph.state import DealState
from app.harness.hooks import NodeContext
from app.harness.policy import evaluate_policy
from app.harness.tools.registry import Tool, ToolRegistry
from app.security.approval import ApprovalError, approval_render, verify_approval


def policy_check(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    decision = evaluate_policy(
        state,
        amount_cap_minor=DEFAULT_CAP,
        payee=_payee(state),
    )
    return {"policy": decision}


DEFAULT_CAP = 1_000_000_00  # USD minor; demo tenant cap


class PayoutInput(BaseModel):
    deal_id: str
    tenant_id: str
    nonce: str
    amount_minor: int = Field(gt=0, strict=True)


class PayoutOutput(BaseModel):
    payout_ref: str


class AnchorInput(BaseModel):
    deal_id: str
    tenant_id: str
    chain_head: str


class AnchorOutput(BaseModel):
    chain_head: str
    tx_ref: str


def execution_registry(ctx: NodeContext) -> ToolRegistry:
    registry = ToolRegistry(audit_sink=ctx.audit)

    def sandbox_payout(raw_args: BaseModel) -> BaseModel:
        args = PayoutInput.model_validate(raw_args)
        return PayoutOutput(payout_ref=f"sandbox-{args.deal_id}-{args.nonce[:8]}")

    registry.register(
        Tool(
            name="execute_sandbox_payout",
            description="Create deterministic sandbox payout reference",
            fn=sandbox_payout,
            input_model=PayoutInput,
            output_model=PayoutOutput,
            side_effect="act",
            allowed_nodes=frozenset({"execute"}),
            llm_callable=False,
        )
    )

    def anchor(raw_args: BaseModel) -> BaseModel:
        args = AnchorInput.model_validate(raw_args)
        if ctx.anchor is None:
            raise RuntimeError("anchor client unavailable")
        receipt = ctx.anchor.anchor(args.chain_head, args.tenant_id)
        return AnchorOutput(chain_head=args.chain_head, tx_ref=receipt.tx_ref)

    registry.register(
        Tool(
            name="anchor_hash",
            description="Anchor an audit chain head",
            fn=anchor,
            input_model=AnchorInput,
            output_model=AnchorOutput,
            side_effect="act",
            allowed_nodes=frozenset({"execute"}),
            llm_callable=False,
        )
    )
    return registry


def _payee(state: DealState) -> str | None:
    for d in state.extracted:
        b = d.get("beneficiary") if d.kind == "commercial_invoice" else None
        if b is not None:
            return str(b.value)
    return None


async def human_approval(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    from langgraph.types import interrupt

    payload = {"kind": "human_approval", **approval_render(state)}
    resume = interrupt(payload)
    # resume payload: {"approval": SignedApproval | None, "note": str}
    approval_data = (resume or {}).get("approval")
    if approval_data is None:
        return {"approval": None}

    from app.graph.state import SignedApproval

    approval = SignedApproval.model_validate(approval_data)
    try:
        if ctx.approval_verifier is None:
            raise ApprovalError("approval verifier is not configured")
        verify_approval(approval, state.deal_id, approval_render(state), ctx.approval_verifier)
    except ApprovalError as e:
        return {"fatal_error": f"approval rejected: {e}"}
    return {"approval": approval}


def _amount(state: DealState) -> int | None:
    for d in state.extracted:
        t = d.get("total_amount") if d.kind == "commercial_invoice" else None
        if t is None:
            continue
        from decimal import Decimal, InvalidOperation

        try:
            return int((Decimal(str(t.value).replace(",", "")) * 100).quantize(Decimal(1)))
        except InvalidOperation:
            return None
    return None


async def execute(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    if (
        state.approval is None
        or ctx.approval_verifier is None
        or state.policy is None
        or state.policy.decision != "allow"
        or state.has_block_findings()
    ):
        return {"fatal_error": "execute preconditions failed"}
    try:
        verify_approval(
            state.approval,
            state.deal_id,
            approval_render(state),
            ctx.approval_verifier,
        )
    except ApprovalError as e:
        return {"fatal_error": f"execute approval verification failed: {e}"}
    amount_minor = _amount(state)
    if amount_minor is None:
        return {"fatal_error": "execute: no payable amount"}

    # Idempotency is mandatory before any act tool is called.
    # Key by the approved state as well as the deal. Changing an unsigned nonce
    # cannot create a second payout for the same signed approval.
    key = f"payout:{state.deal_id}:{state.approval.deal_hash}"
    if ctx.redis is None:
        return {"fatal_error": "execute requires an idempotency store"}
    if not ctx.redis.set(f"{key}:lock", "1", nx=True, ex=86400):
        return {"fatal_error": "execute: duplicate submission blocked by idempotency key"}

    registry = execution_registry(ctx)
    head = ctx.audit.head(state.tenant_id)
    anchor = registry.call(
        "execute",
        "anchor_hash",
        AnchorInput(
            deal_id=state.deal_id,
            tenant_id=state.tenant_id,
            chain_head=head,
        ),
    )
    payout_result = registry.call(
        "execute",
        "execute_sandbox_payout",
        PayoutInput(
            deal_id=state.deal_id,
            tenant_id=state.tenant_id,
            nonce=state.approval.nonce,
            amount_minor=amount_minor,
        ),
    )
    if not isinstance(payout_result, PayoutOutput) or not isinstance(anchor, AnchorOutput):
        return {"fatal_error": "execution tool returned an invalid output"}
    payout = payout_result

    from app.calc.money import Money
    from app.graph.state import Receipt, new_id

    return {
        "receipt": Receipt(
            receipt_id=new_id("rcpt"),
            deal_id=state.deal_id,
            payout_ref=payout.payout_ref,
            amount=Money(minor=amount_minor, currency="USD"),
            anchored_hash=anchor.chain_head,
            anchor_tx=anchor.tx_ref,
            executed_at=state.approval.signed_at,
        )
    }


async def escalate(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    if state.fatal_error:
        return {"escalation_reason": state.fatal_error}
    if state.blocked_by_injection():
        return {"escalation_reason": "prompt injection detected in documents"}
    blocks = [f.summary for f in state.findings if f.severity == "block" and f.status == "open"]
    if blocks:
        return {"escalation_reason": f"unresolved block findings: {'; '.join(blocks[:3])}"}
    if state.policy and state.policy.decision != "allow":
        return {"escalation_reason": f"policy {state.policy.decision}: {state.policy.reason}"}
    return {"escalation_reason": "escalated without a specific reason (fail closed)"}


async def report(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    open_findings = [f"{f.severity}: {f.summary}" for f in state.findings if f.status == "open"]
    waived = [f.summary for f in state.findings if f.status == "waived"]
    parts = ["SYNTHETIC DATA — deal review complete."]
    parts.append(f"Findings: {len(open_findings)} open, {len(waived)} waived.")
    if open_findings:
        parts.extend(open_findings)
    if state.fx_options:
        best = max(state.fx_options, key=lambda option: option.net_minor)
        parts.append(
            f"Best synthetic FX route: {best.route_id}, net {best.net_minor} minor "
            f"{best.buy_currency}."
        )
    if state.cash_projection is not None:
        cash = state.cash_projection
        parts.append(
            f"Cash trough: {cash.min_balance_minor} minor {cash.currency} "
            f"on day {cash.min_balance_day}; {cash.days_below_zero} days below zero."
        )
    if state.finance_offer is not None:
        offer = state.finance_offer
        parts.append(
            f"Synthetic finance offer: net {offer.net_proceeds.minor} minor "
            f"{offer.net_proceeds.currency}; total cost {offer.total_cost.minor} minor."
        )
    if state.policy is not None:
        parts.append(f"Policy decision: {state.policy.decision}.")
    if state.receipt is not None:
        parts.append(f"Sandbox payout receipt: {state.receipt.receipt_id}.")
    elif state.escalation_reason:
        parts.append(f"Escalated: {state.escalation_reason}")
    return {"report_summary": "\n".join(parts)}
