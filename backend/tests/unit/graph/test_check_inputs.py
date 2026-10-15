"""Compliance and verify must see identical battery inputs (gap 1)."""

from __future__ import annotations

from app.graph.check_inputs import lc_check_inputs
from app.graph.nodes.verify import _recompute_check_ids
from app.graph.state import DealState, ExtractedDoc, ExtractedField, SourceRef


def doc(kind: str, **fields: str) -> ExtractedDoc:
    return ExtractedDoc(
        doc_id=f"doc_{kind}",
        sha256=kind,
        kind=kind,  # type: ignore[arg-type]
        fields=[
            ExtractedField(name=k, value=v, confidence=0.99, source=SourceRef(page=1))
            for k, v in fields.items()
        ],
        extraction_model="t",
    )


def state(*docs: ExtractedDoc) -> DealState:
    return DealState(deal_id="d", tenant_id="t", extracted=list(docs))


def test_schedule_fills_missing_invoice_fields():
    s = state(
        doc("letter_of_credit", expiry_date="2026-12-31"),
        doc("commercial_invoice", total_amount="1.00"),
        doc("presentation_schedule", presentation_date="2026-11-09", shipment_date="2026-11-01"),
    )
    lc, inv = lc_check_inputs(s)
    assert lc == {"expiry_date": "2026-12-31"}
    assert inv["presentation_date"] == "2026-11-09"
    assert inv["shipment_date"] == "2026-11-01"


def test_invoice_values_win_over_the_schedule():
    s = state(
        doc("commercial_invoice", shipment_date="2026-11-01"),
        doc("presentation_schedule", shipment_date="2026-12-25"),
    )
    assert lc_check_inputs(s)[1]["shipment_date"] == "2026-11-01"


def test_no_schedule_leaves_invoice_untouched():
    s = state(doc("commercial_invoice", total_amount="1.00"))
    assert lc_check_inputs(s)[1] == {"total_amount": "1.00"}


def test_verify_recomputes_late_presentation_from_the_same_inputs():
    s = state(
        doc("letter_of_credit", expiry_date="2026-12-31"),
        doc("commercial_invoice", shipment_date="2026-11-01"),
        doc("presentation_schedule", presentation_date="2026-11-30"),
    )
    assert "ucp-late-presentation" in _recompute_check_ids(s)
