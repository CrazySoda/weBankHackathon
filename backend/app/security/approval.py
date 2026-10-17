"""Approval signing and verification (BUILD_PLAN M6).

`deal_hash` = canonical sha256 over EXACTLY what the approval screen renders
(findings, waivers, injection flags, FX options, finance offer, payee, amount). The human signs
this hash with their passkey/SOTER key (ed25519 in the demo). Verification:

 1. signature must verify against the approver's key over deal_hash
 2. the deal_hash must equal the hash of the CURRENT rendered state — any
    state change after signing invalidates the approval
 3. the nonce is single-use (Redis SETNX upstream; checked again in execute)
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from app.calc.money import canonical_json, sha256_hex
from app.graph.state import DealState, SignedApproval
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

REPLAY_WINDOW_S = 300

# DEMO FIXTURE, NOT A SECRET. This committed key is forgeable by anyone with
# the repository and must never be used outside a local synthetic demo.
DEMO_APPROVER_ID = "owner-1"
DEMO_PUBLIC_KEY_B64 = "5OT3skRSnCuBbaeqC7PCGVBpm5AEtjGMQd7hEaC3Q6U="
DEMO_PRIVATE_KEY_B64 = "KzeqNDJ6tzl6HXK6npZcgkxon1xSpQnzGK9WNfBXGFU="


class ApprovalError(Exception):
    """Approval rejected — fail closed, escalate."""


def deal_hash(render: dict[str, Any]) -> str:
    """Canonical hash of the approval screen's render dict."""
    return sha256_hex(canonical_json(render))


def approval_render(state: DealState) -> dict[str, Any]:
    """Canonical public approval screen data shared by API and graph."""
    amount_minor = None
    for doc in state.extracted:
        field = doc.get("total_amount") if doc.kind == "commercial_invoice" else None
        if field is not None:
            from decimal import Decimal, InvalidOperation

            try:
                amount_minor = int(
                    (Decimal(str(field.value).replace(",", "")) * 100).quantize(Decimal(1))
                )
            except InvalidOperation:
                amount_minor = None
            break
    return {
        "deal_id": state.deal_id,
        "findings": [
            {
                "check_id": f.check_id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "status": f.status,
                "summary": f.summary,
                "explanation": f.explanation,
                "evidence": [e.model_dump(mode="json") for e in f.evidence],
            }
            for f in state.findings
        ],
        "waivers": [f.model_dump(mode="json") for f in state.findings if f.status == "waived"],
        # DECISION: warn-level injection flags (e.g. beneficiary-change language) do not
        # escalate, so the approver must see them. They are part of the signed render:
        # a flag added or removed after signing invalidates the approval.
        "injection_flags": [f.model_dump(mode="json") for f in state.injection_flags],
        "fx_options": [o.model_dump(mode="json") for o in state.fx_options],
        "finance_offer": (
            state.finance_offer.model_dump(mode="json") if state.finance_offer else None
        ),
        "payee": next(
            (
                str(d.get("beneficiary").value)
                for d in state.extracted
                if d.kind == "commercial_invoice" and d.get("beneficiary") is not None
            ),
            None,
        ),
        "amount_minor": amount_minor,
        "policy": state.policy.model_dump(mode="json") if state.policy else None,
    }


def approval_signature_message(approval: SignedApproval) -> bytes:
    """Bind the signature to the deal, signer, method, timestamp, and nonce."""
    return canonical_json(
        {
            "deal_hash": approval.deal_hash,
            "approver_id": approval.approver_id,
            "method": approval.method,
            "signed_at": approval.signed_at,
            "nonce": approval.nonce,
        }
    ).encode("utf-8")


def sign_approval(approval: SignedApproval, private_key: ed25519.Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(approval_signature_message(approval))).decode("ascii")


class ApprovalVerifier:
    """Verifier bound to the approver registry (demo: injected key map)."""

    def __init__(self, approver_keys: dict[str, ed25519.Ed25519PublicKey]):
        self.approver_keys = approver_keys

    def verify(
        self, approval: SignedApproval, current_render: dict[str, Any], now: datetime | None = None
    ) -> None:
        # 1. approver known
        key = self.approver_keys.get(approval.approver_id)
        if key is None:
            raise ApprovalError(f"unknown approver {approval.approver_id!r}")

        # 2. current state must match the approval hash
        current = deal_hash(current_render)
        if current != approval.deal_hash:
            raise ApprovalError("deal state changed after signing — approval invalidated")

        # 3. every approval metadata field is signed too
        try:
            key.verify(
                base64.b64decode(approval.signature_b64, validate=True),
                approval_signature_message(approval),
            )
        except (InvalidSignature, ValueError) as e:
            raise ApprovalError(f"signature invalid: {e}") from e

        # 4. freshness (replay window)
        try:
            signed_at = datetime.fromisoformat(approval.signed_at)
        except ValueError as e:
            raise ApprovalError("signed_at is not ISO 8601") from e
        now = now or datetime.now(UTC)
        age = (now - signed_at).total_seconds()
        if age < 0 or age > REPLAY_WINDOW_S:
            raise ApprovalError(f"approval expired ({age:.0f}s > {REPLAY_WINDOW_S}s)")


def verify_approval(
    approval: SignedApproval,
    expected_deal_id: str,
    current_render: dict[str, Any],
    verifier: ApprovalVerifier | None = None,
) -> None:
    """Verify the signature and exact approval-screen representation."""
    if not approval.signature_b64:
        raise ApprovalError("empty signature")
    if not approval.deal_hash:
        raise ApprovalError("empty deal hash")
    if not approval.approver_id:
        raise ApprovalError("no approver")
    if not approval.nonce:
        raise ApprovalError("missing nonce (idempotency key)")
    if current_render.get("deal_id") != expected_deal_id:
        raise ApprovalError("current approval render references a different deal")
    if verifier is None:
        raise ApprovalError("approval verifier is not configured")
    verifier.verify(approval, current_render)
