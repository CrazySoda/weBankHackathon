"""Image and scanned-PDF documents are read by the `vision` alias, never by a text model, and
always park the deal for a human (DECISIONS #27)."""

from __future__ import annotations

import base64
import io

import pytest
from app.graph.nodes.extract_doc import ExtractionOutput, FieldOut, extract_doc
from app.graph.state import DealState, DocRef
from app.harness.document_parsing import render_pdf_pages

from tests.graph.conftest import make_pdf

# a valid 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

FIELDS = [
    FieldOut(name="beneficiary", value="SHENZHEN SUNNY CO", confidence=1.0, snippet="SHENZHEN"),
    FieldOut(name="total_amount", value="100,000.00", confidence=1.0, snippet="100,000.00"),
]


def blank_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def image_ref(sha: str, mime: str = "image/png", name: str = "scan.png") -> DocRef:
    return DocRef(
        doc_id="d-img",
        deal_id="d1",
        sha256=sha,
        filename=name,
        mime=mime,
        size_bytes=len(PNG),
        kind="commercial_invoice",
    )  # type: ignore[arg-type]


def state_for(ref: DocRef) -> DealState:
    return DealState(deal_id="d1", tenant_id="t1", documents=[ref], pending_doc=ref)


@pytest.fixture()
def vision_ctx(ctx):
    ctx.vision_enabled = True
    return ctx


def capture(fake_llm, kind="bill_of_lading"):
    seen: dict = {}

    def hook(messages):
        seen["messages"] = messages
        return ExtractionOutput(kind=kind, fields=list(FIELDS))

    fake_llm.hooks["ExtractionOutput"] = hook
    return seen


class TestImageDocuments:
    async def test_without_a_vision_alias_no_model_reads_the_image(self, ctx, fake_llm, docs_store):
        sha = docs_store.put(PNG)
        update = await extract_doc(state_for(image_ref(sha)), ctx)
        doc = update["extracted"][0]
        assert doc.extraction_model == "unsupported-image"
        assert doc.fields == [] and doc.low_confidence
        assert fake_llm.calls == []  # nothing was sent to any model

    async def test_vision_reads_the_image_and_identifies_it(self, vision_ctx, fake_llm, docs_store):
        seen = capture(fake_llm, kind="bill_of_lading")
        sha = docs_store.put(PNG)
        update = await extract_doc(state_for(image_ref(sha)), vision_ctx)

        assert fake_llm.calls == [("vision", "ExtractionOutput")]  # never the text alias
        doc = update["extracted"][0]
        assert doc.kind == "bill_of_lading"  # from the image, not the "invoice" hint
        assert doc.extraction_model == "vision:fake-primary"
        assert {f.name for f in doc.fields} == {"beneficiary", "total_amount"}
        content = seen["messages"][0]["content"]
        assert content[0]["type"] == "text" and "untrusted" in content[0]["text"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert len(update["served_by"]) == 1

    async def test_values_read_from_an_image_are_never_trusted(
        self, vision_ctx, fake_llm, docs_store
    ):
        capture(fake_llm)
        sha = docs_store.put(PNG)
        doc = (await extract_doc(state_for(image_ref(sha)), vision_ctx))["extracted"][0]
        assert doc.low_confidence  # so the router parks the deal for a human
        assert all(f.source.snippet == "" for f in doc.fields)  # nothing to ground a quote in

    async def test_unknown_kind_falls_back_to_the_uploaded_hint(
        self, vision_ctx, fake_llm, docs_store
    ):
        capture(fake_llm, kind="unknown")
        sha = docs_store.put(PNG)
        doc = (await extract_doc(state_for(image_ref(sha)), vision_ctx))["extracted"][0]
        assert doc.kind == "commercial_invoice"

    async def test_jpeg_keeps_its_mime_type(self, vision_ctx, fake_llm, docs_store):
        seen = capture(fake_llm)
        sha = docs_store.put(PNG)
        await extract_doc(state_for(image_ref(sha, mime="image/jpeg", name="x.jpg")), vision_ctx)
        url = seen["messages"][0]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")


class TestScannedPdf:
    async def test_pdf_without_a_text_layer_is_rendered_and_read_by_vision(
        self, vision_ctx, fake_llm, docs_store
    ):
        seen = capture(fake_llm)
        sha = docs_store.put(blank_pdf())
        ref = image_ref(sha, mime="application/pdf", name="scan.pdf")
        update = await extract_doc(state_for(ref), vision_ctx)
        assert fake_llm.calls == [("vision", "ExtractionOutput")]
        url = seen["messages"][0]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        assert update["extracted"][0].extraction_model.startswith("vision:")

    async def test_pdf_with_a_text_layer_never_goes_to_vision(
        self, vision_ctx, fake_llm, docs_store
    ):
        fake_llm.hooks["ExtractionOutput"] = lambda _m: ExtractionOutput(
            kind="commercial_invoice", fields=list(FIELDS)
        )
        sha = docs_store.put(make_pdf(["COMMERCIAL INVOICE SHENZHEN SUNNY CO 100,000.00"]))
        ref = image_ref(sha, mime="application/pdf", name="inv.pdf")
        await extract_doc(state_for(ref), vision_ctx)
        assert fake_llm.calls and all(alias == "fast" for alias, _ in fake_llm.calls)

    def test_render_pdf_pages_returns_png_pages(self):
        pages = render_pdf_pages(blank_pdf())
        assert len(pages) == 1 and pages[0].startswith(b"\x89PNG")
