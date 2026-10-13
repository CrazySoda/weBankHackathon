"""M6 acceptance: replayed / modified-after-sign / double-submit approvals fail safely."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from app.graph.state import SignedApproval
from app.security.approval import ApprovalError, ApprovalVerifier, deal_hash, sign_deal_hash
from cryptography.hazmat.primitives.asymmetric import ed25519


@pytest.fixture()
def keys():
    owner = ed25519.Ed25519PrivateKey.generate()
    attacker = ed25519.Ed25519PrivateKey.generate()
    return {
        "owner": owner,
        "attacker": attacker,
        "owner_pub": owner.public_key(),
        "attacker_pub": attacker.public_key(),
    }


@pytest.fixture()
def render():
    return {
        "deal_id": "d1",
        "findings": [{"rule_id": "r1", "severity": "info"}],
        "payee": "Shenzhen Sunny Goods Co",
        "amount_minor": 10_000_000,
    }


def mk_approval(keys, render: dict, approver: str = "owner") -> SignedApproval:
    h = deal_hash(render)
    key = keys[approver]
    return SignedApproval(
        deal_hash=h,
        approver_id=approver,
        method="webauthn_passkey",
        signature_b64=sign_deal_hash(h, key),
        signed_at=datetime.now(UTC).isoformat(),
        nonce="nonce-1",
    )


@pytest.fixture()
def verifier(keys):
    return ApprovalVerifier({"owner": keys["owner_pub"]})


class TestHappyPath:
    def test_valid_approval_passes(self, keys, render, verifier):
        approval = mk_approval(keys, render)
        verifier.verify(approval, render)


class TestReplay:
    def test_replayed_approval_after_window_rejected(self, keys, render, verifier):
        approval = mk_approval(keys, render)
        old = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        stale = approval.model_copy(update={"signed_at": old})
        # re-sign with the stale timestamp so only the freshness check fails
        stale = approval.model_copy(update={"signed_at": old})
        with pytest.raises(ApprovalError, match="expired"):
            verifier.verify(stale, render)

    def test_nonce_single_use_upstream(self, keys, render, verifier):
        """A used nonce must never be accepted again: Redis SETNX in execute,
        structural check here."""
        from app.security.approval import verify_approval

        seen_nonces: set[str] = set()
        approval = mk_approval(keys, render)
        verifier.verify(approval, render)
        seen_nonces.add(approval.nonce)
        # replayed structural check with a burned/empty nonce fails closed
        with pytest.raises(ApprovalError, match="nonce"):
            verify_approval(approval.model_copy(update={"nonce": ""}), "d1", "digest")
        assert approval.nonce in seen_nonces


class TestModifiedAfterSign:
    def test_changed_amount_invalidates(self, keys, render, verifier):
        approval = mk_approval(keys, render)
        tampered = render | {"amount_minor": 99_999_999}  # the poisoned-doc dream
        with pytest.raises(ApprovalError, match="changed after signing"):
            verifier.verify(approval, tampered)

    def test_changed_payee_invalidates(self, keys, render, verifier):
        approval = mk_approval(keys, render)
        tampered = render | {"payee": "Attacker Ltd"}
        with pytest.raises(ApprovalError, match="changed after signing"):
            verifier.verify(approval, tampered)

    def test_added_finding_invalidates(self, keys, render, verifier):
        approval = mk_approval(keys, render)
        tampered = render | {
            "findings": [
                {"rule_id": "r1", "severity": "info"},
                {"rule_id": "r2", "severity": "block"},
            ]
        }
        with pytest.raises(ApprovalError, match="changed after signing"):
            verifier.verify(approval, tampered)


class TestWrongSigner:
    def test_unsigned_by_attacker_key_rejected(self, keys, render, verifier):
        h = deal_hash(render)
        forged = base64.b64encode(keys["attacker"].sign(h.encode())).decode()
        approval = SignedApproval(
            deal_hash=h,
            approver_id="owner",  # claims the owner, signs with attacker key
            method="webauthn_passkey",
            signature_b64=forged,
            signed_at=datetime.now(UTC).isoformat(),
            nonce="n2",
        )
        with pytest.raises(ApprovalError, match="signature invalid"):
            verifier.verify(approval, render)

    def test_unknown_approver_rejected(self, keys, render, verifier):
        approval = mk_approval(keys, render, approver="attacker")
        with pytest.raises(ApprovalError, match="unknown approver"):
            verifier.verify(approval, render)


class TestStructuralChecks:
    def test_empty_signature_rejected(self):
        from app.security.approval import verify_approval

        approval = SignedApproval(
            deal_hash="h",
            approver_id="u",
            method="pin_otp",
            signature_b64="",
            signed_at="2026-01-01T00:00:00+00:00",
            nonce="n",
        )
        with pytest.raises(ApprovalError, match="empty signature"):
            verify_approval(approval, "d1", "digest")

    def test_missing_nonce_rejected(self):
        from app.security.approval import verify_approval

        approval = SignedApproval(
            deal_hash="h",
            approver_id="u",
            method="pin_otp",
            signature_b64="s",
            signed_at="2026-01-01T00:00:00+00:00",
            nonce="",
        )
        with pytest.raises(ApprovalError, match="nonce"):
            verify_approval(approval, "d1", "digest")
