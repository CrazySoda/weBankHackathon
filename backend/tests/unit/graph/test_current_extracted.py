"""A corrected upload must supersede the flawed original, whatever the ids sort like.

Regression: consumers used to take the first extraction of a kind in sha256 order, so
after a corrected-document upload the stale invoice was picked about half the time.
"""

from __future__ import annotations

import pytest
from app.graph.state import (
    DealState,
    DocRef,
    ExtractedDoc,
    ExtractedField,
    SourceRef,
    merge_doc_refs,
)


def _ref(doc_id: str, kind: str = "commercial_invoice") -> DocRef:
    return DocRef(
        doc_id=doc_id,
        deal_id="d1",
        sha256="0" * 64,
        filename=f"{doc_id}.pdf",
        mime="application/pdf",
        size_bytes=1,
        kind=kind,  # type: ignore[arg-type]
    )


def _extracted(doc_id: str, total: str, sha: str, kind: str = "commercial_invoice") -> ExtractedDoc:
    return ExtractedDoc(
        doc_id=doc_id,
        sha256=sha,
        kind=kind,  # type: ignore[arg-type]
        fields=[
            ExtractedField(
                name="total_amount",
                value=total,
                confidence=0.99,
                source=SourceRef(page=1, snippet=total),
            )
        ],
        extraction_model="test",
    )


@pytest.mark.parametrize(
    ("old_id", "new_id", "old_sha", "new_sha"),
    [
        ("doc_aaa", "doc_zzz", "a" * 64, "b" * 64),  # ids and hashes sort old-first
        ("doc_zzz", "doc_aaa", "b" * 64, "a" * 64),  # ...and new-first
        ("doc_aaa", "doc_zzz", "b" * 64, "a" * 64),
        ("doc_zzz", "doc_aaa", "a" * 64, "b" * 64),
    ],
)
def test_latest_upload_of_a_kind_is_the_one_in_effect(old_id, new_id, old_sha, new_sha):
    state = DealState(
        deal_id="d1",
        tenant_id="t1",
        documents=[_ref(old_id), _ref(new_id)],  # upload order: old, then corrected
        extracted=[
            _extracted(old_id, "120000.00", old_sha),
            _extracted(new_id, "100000.00", new_sha),
        ],
    )
    current = state.current_extracted
    assert [d.doc_id for d in current] == [new_id]
    assert current[0].get("total_amount").value == "100000.00"  # type: ignore[union-attr]
    assert len(state.extracted) == 2  # the superseded read stays for the audit trail


def test_other_kinds_are_unaffected():
    state = DealState(
        deal_id="d1",
        tenant_id="t1",
        documents=[_ref("doc_lc", "letter_of_credit"), _ref("doc_inv")],
        extracted=[
            _extracted("doc_lc", "100000.00", "c" * 64, "letter_of_credit"),
            _extracted("doc_inv", "100000.00", "d" * 64),
        ],
    )
    assert {d.kind for d in state.current_extracted} == {"letter_of_credit", "commercial_invoice"}


def test_merge_doc_refs_keeps_upload_order():
    merged = merge_doc_refs([_ref("doc_zzz")], [_ref("doc_aaa")])
    assert [d.doc_id for d in merged] == ["doc_zzz", "doc_aaa"]
