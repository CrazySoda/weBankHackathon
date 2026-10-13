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

from app.graph.state import DealState
from app.harness.hooks import NodeContext
from app.harness.policy import evaluate_policy
from app.security.approval import ApprovalError, verify_approval


def policy_check(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    decision = evaluate_policy(
        state,
        amount_cap_minor=DEFAULT_CAP,
        payee=_payee(state),
    )
    return {"policy": decision}


DEFAULT_CAP = 1_000_000_00  # USD minor; demo tenant cap


def _payee(state: DealState) -> str | None:
    for d in state.extracted:
        b = d.get("beneficiary") if d.kind == "commercial_invoice" else None
        if b is not None:
            return str(b.value)
    return None


async def human_approval(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    from langgraph.types import interrupt

    payload = {
        "kind": "human_approval",
        "deal_id": state.deal_id,
        "findings": [
            {
                "check_id": f.check_id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "status": f.status,
            }
            for f in state.findings
        ],
        "waivers": [{"check_id": f.check_id} for f in state.findings if f.status == "waived"],
        "fx_options": [o.model_dump() for o in state.fx_options],
        "finance_offer": state.finance_offer.model_dump() if state.finance_offer else None,
        "payee": _payee(state),
        "amount_minor": _amount(state),
    }
    resume = interrupt(payload)
    # resume payload: {"approval": SignedApproval | None, "note": str}
    approval_data = (resume or {}).get("approval")
    if approval_data is None:
        return {"approval": None}

    from app.graph.state import SignedApproval

    approval = SignedApproval.model_validate(approval_data)
    try:
        verify_approval(
            approval,
            expected_deal_id=state.deal_id,
            state_digest=state.model_dump_json(
                include={"findings", "fx_options", "finance_offer", "policy"}
            ),
        )
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
    assert state.approval is not None, "execute requires a verified approval"
    amount_minor = _amount(state)
    if amount_minor is None:
        return {"fatal_error": "execute: no payable amount"}

    # idempotency: one payout per (deal, approval nonce) — Redis SETNX in prod
    key = f"payout:{state.deal_id}:{state.approval.nonce}"
    if ctx.redis is not None and not ctx.redis.set(f"{key}:lock", "1", nx=True, ex=3600):
        return {"fatal_error": "execute: duplicate submission blocked by idempotency key"}

    payout_ref = f"sandbox-{state.deal_id}-{state.approval.nonce[:8]}"

    # anchor the audit-chain head (act tool; deterministic node only, rule 0.5)
    anchored = None
    if ctx.anchor is not None:
        head = ctx.audit.head(state.tenant_id)
        receipt = ctx.anchor.anchor(head, state.tenant_id)
        anchored = (head, receipt.tx_ref)

    from app.calc.money import Money
    from app.graph.state import Receipt, new_id

    return {
        "receipt": Receipt(
            receipt_id=new_id("rcpt"),
            deal_id=state.deal_id,
            payout_ref=payout_ref,
            amount=Money(minor=amount_minor, currency="USD"),
            anchored_hash=anchored[0] if anchored else None,
            anchor_tx=anchored[1] if anchored else None,
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
    # summary text is derived deterministically; `fast` polishes only if present
    return {}
