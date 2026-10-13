"""Shared fixtures for graph tests: fake LLM, PDF builder, docs store."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from app.audit.events import InMemoryAuditSink
from app.graph.state import ModelUse
from app.harness.budget import DealBudget
from app.harness.hooks import NodeContext
from app.harness.llm import CompletionResult
from app.security.storage import DocumentStore


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
        allow_degraded=True,
        temperature=0.0,
        max_tokens=4096,
    ):
        self.calls.append((alias, output_model.__name__))
        hook = self.hooks.get(output_model.__name__)
        out = hook(messages) if hook is not None else self.responses.get(output_model.__name__)
        if out is None:
            out = self._default(output_model)
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

    def _default(self, model: type):
        name = model.__name__
        if name == "ExtractionOutput":
            return model()
        if name == "ClassifierVerdict":
            return model(injection_suspected=False)
        if name == "PlanOutput":
            return model(
                chosen_skills=["lc-ucp600-check", "cn-export-vat-refund"],
                rationale="LC present; CN exporter",
            )
        if name == "Explainer":
            return model(explanations=["explained"] * 20)
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
def ctx(fake_llm: FakeLLM, docs_store: DocumentStore) -> NodeContext:
    return NodeContext(
        budget=DealBudget("d1", max_steps=200, max_tokens=10**9, max_cost_minor=10**9),
        audit=InMemoryAuditSink(),
        llm=fake_llm,
        docs=docs_store,
    )
