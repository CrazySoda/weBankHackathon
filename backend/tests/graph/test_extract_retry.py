"""extract_doc retries once when a model returns a sparse extraction (live regression:
1 field from an invoice made the deal fail at the policy with no useful reason)."""

from __future__ import annotations

from app.graph.nodes.extract_doc import ExtractionOutput, FieldOut, extract_doc
from app.graph.state import DealState

from tests.graph.conftest import make_pdf
from tests.graph.test_graph import INV_FIELDS, docref

SPARSE = [FieldOut(name="currency", value="USD", confidence=0.99, snippet="USD", page=1)]


async def _run(ctx, fake_llm, docs_store, outputs: list[list[FieldOut]]):
    queue = list(outputs)

    def hook(_messages):
        return ExtractionOutput(kind="commercial_invoice", fields=queue.pop(0))

    fake_llm.hooks["ExtractionOutput"] = hook
    sha = docs_store.put(make_pdf(["COMMERCIAL INVOICE USD 100,000.00"]))
    pending = docref("d1", sha, "inv.pdf", kind="commercial_invoice")
    state = DealState(deal_id="d1", tenant_id="t1", documents=[pending], pending_doc=pending)
    update = await extract_doc(state, ctx)
    calls = sum(1 for _, name in fake_llm.calls if name == "ExtractionOutput")
    return update, calls


async def test_sparse_extraction_is_retried_once(ctx, fake_llm, docs_store):
    update, calls = await _run(ctx, fake_llm, docs_store, [SPARSE, INV_FIELDS])
    assert calls == 2
    names = {f.name for f in update["extracted"][0].fields}
    assert {"total_amount", "beneficiary"} <= names
    assert len(update["served_by"]) == 2  # both model calls are recorded


async def test_complete_extraction_is_not_retried(ctx, fake_llm, docs_store):
    update, calls = await _run(ctx, fake_llm, docs_store, [INV_FIELDS])
    assert calls == 1
    assert len(update["served_by"]) == 1


async def test_a_worse_retry_does_not_replace_the_first_answer(ctx, fake_llm, docs_store):
    partial = [f for f in INV_FIELDS if f.name != "beneficiary"]  # has total_amount only
    update, calls = await _run(ctx, fake_llm, docs_store, [partial, SPARSE])
    assert calls == 2
    assert "total_amount" in {f.name for f in update["extracted"][0].fields}


async def test_still_sparse_after_the_retry_is_left_to_fail_closed(ctx, fake_llm, docs_store):
    update, calls = await _run(ctx, fake_llm, docs_store, [SPARSE, SPARSE])
    assert calls == 2  # bounded: never more than one retry
    assert {f.name for f in update["extracted"][0].fields} == {"currency"}
