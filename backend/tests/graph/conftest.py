"""Shared fixtures for graph tests: fake LLM, PDF builder, docs store."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.audit.anchor import MockAnchor
from app.audit.events import InMemoryAuditSink
from app.graph.state import ModelUse, SignedApproval
from app.harness.budget import DealBudget
from app.harness.hooks import NodeContext
from app.harness.llm import CompletionResult
from app.security.approval import ApprovalVerifier, deal_hash, sign_approval
from app.security.storage import DocumentStore
from cryptography.hazmat.primitives.asymmetric import ed25519


class FakeLLM:
    """Scripted LLM: keyed by output_model class name; falls back to defaults.

    `hooks[model_name]` receives the messages and returns an output instance —
    used where one output model must vary per call (e.g. extraction by doc hint).
    """

    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.hooks: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []  # (alias, model name)

    async def complete(
        self,
        *,
        alias,
        system,
        messages,
        output_model,
        node="",
        prompt_version="",
        allow_degraded=True,
        temperature=0.0,
        max_tokens=4096,
    ):
        self.calls.append((alias, output_model.__name__))
        hook = self.hooks.get(output_model.__name__)
        out = hook(messages) if hook is not None else self.responses.get(output_model.__name__)
        if out is None:
            out = self._default(output_model, messages)
        if isinstance(out, Exception):
            raise out
        return CompletionResult(
            output=out,
            use=ModelUse(
                node=node,
                alias=alias,
                deployment="fake-primary",
                prompt_tokens=10,
                completion_tokens=5,
            ),
            raw_text="",
        )

    def _default(self, model: type, messages=None):
        name = model.__name__
        if name == "ExtractionOutput":
            return model()
        if name == "ClassifierOutput":
            import re

            content = str(messages[-1]["content"]) if messages else ""
            ids = re.findall(r"'doc_id': '([^']+)'", content)
            return model(verdicts=[{"doc_id": doc_id} for doc_id in ids])
        if name == "PlanOutput":
            return model(
                chosen_skills=["lc-ucp600-check", "cn-export-vat-refund"],
                rationale="LC present; CN exporter",
            )
        if name == "Explainer":
            n = str(messages[-1]["content"]).count("- [") if messages else 0
            return model(explanations=["explained"] * n)
        if name == "VerifyOutput":
            return model(verdicts=[])
        if name == "AmendmentDraft":
            return model(subject="Amendment request", body="Please correct the invoice total.")
        return model()


def make_pdf(lines: list[str], white_lines: list[str] | None = None) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11, color=(0, 0, 0))
        y += 16
    for line in white_lines or []:
        page.insert_text((72, y), line, fontsize=11, color=(1, 1, 1))
        y += 16
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.fixture()
def docs_store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(tmp_path / "docs")


@pytest.fixture()
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture()
def owner_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture()
def ctx(fake_llm: FakeLLM, docs_store: DocumentStore, owner_key) -> NodeContext:
    import fakeredis

    return NodeContext(
        budget=DealBudget("d1", max_steps=200, max_tokens=10**9, max_cost_minor=10**9),
        audit=InMemoryAuditSink(),
        llm=fake_llm,
        docs=docs_store,
        redis=fakeredis.FakeRedis(),
        anchor=MockAnchor(),
        approval_verifier=ApprovalVerifier({"owner": owner_key.public_key()}),
    )


def sign_for(interrupt_value: dict[str, Any], key: ed25519.Ed25519PrivateKey) -> dict[str, Any]:
    """Sign exactly what the approval screen rendered (the interrupt payload)."""
    render = {k: v for k, v in interrupt_value.items() if k != "kind"}
    approval = SignedApproval(
        deal_hash=deal_hash(render),
        approver_id="owner",
        method="webauthn_passkey",
        signature_b64="",
        signed_at=datetime.now(UTC).isoformat(),
        nonce="nonce-1",
    )
    approval = approval.model_copy(update={"signature_b64": sign_approval(approval, key)})
    return approval.model_dump(mode="json")
