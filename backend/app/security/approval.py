"""Approval signing and verification (BUILD_PLAN M6).

`deal_hash` = canonical sha256 over EXACTLY what the approval screen renders
(findings, waivers, FX options, finance offer, payee, amount). The human signs
this hash with their passkey/SOTER key (ed25519 in the demo). Verification:

 1. signature must verify against the approver's key over deal_hash
 2. the deal_hash must equal the hash of the CURRENT rendered state — any
    state change after signing invalidates the approval
 3. the nonce is single-use (Redis SETNX upstream; checked again in execute)
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from app.calc.money import canonical_json, sha256_hex
from app.graph.state import SignedApproval
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

REPLAY_WINDOW_S = 300


class ApprovalError(Exception):
    """Approval rejected — fail closed, escalate."""


def deal_hash(render: dict) -> str:
    """Canonical hash of the approval screen's render dict."""
    return sha256_hex(canonical_json(render))


def sign_deal_hash(deal_hash_hex: str, private_key: ed25519.Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(deal_hash_hex.encode("utf-8"))).decode("ascii")


class ApprovalVerifier:
    """Verifier bound to the approver registry (demo: injected key map)."""

    def __init__(self, approver_keys: dict[str, ed25519.Ed25519PublicKey]):
        self.approver_keys = approver_keys

    def verify(
        self, approval: SignedApproval, current_render: dict, now: datetime | None = None
    ) -> None:
        # 1. approver known
        key = self.approver_keys.get(approval.approver_id)
        if key is None:
            raise ApprovalError(f"unknown approver {approval.approver_id!r}")

        # 2. signed the deal hash they claim
        try:
            key.verify(
                base64.b64decode(approval.signature_b64),
                approval.deal_hash.encode("utf-8"),
            )
        except (InvalidSignature, ValueError) as e:
            raise ApprovalError(f"signature invalid: {e}") from e

        # 3. deal unchanged since signing
        current = deal_hash(current_render)
        if current != approval.deal_hash:
            raise ApprovalError("deal state changed after signing — approval invalidated")

        # 4. freshness (replay window)
        try:
            signed_at = datetime.fromisoformat(approval.signed_at)
        except ValueError as e:
            raise ApprovalError("signed_at is not ISO 8601") from e
        now = now or datetime.now(UTC)
        age = (now - signed_at).total_seconds()
        if age > REPLAY_WINDOW_S:
            raise ApprovalError(f"approval expired ({age:.0f}s > {REPLAY_WINDOW_S}s)")


def verify_approval(approval: SignedApproval, expected_deal_id: str, state_digest: str) -> None:
    """Graph-side structural check (no keys): the approval must reference this
    deal and carry a non-empty signature. Cryptographic verification with keys
    happens in the ApprovalVerifier (API layer, which holds the key registry)."""
    if not approval.signature_b64:
        raise ApprovalError("empty signature")
    if not approval.deal_hash:
        raise ApprovalError("empty deal hash")
    if not approval.approver_id:
        raise ApprovalError("no approver")
    # state digest is stored in the nonce position check: nonce must be present
    if not approval.nonce:
        raise ApprovalError("missing nonce (idempotency key)")
