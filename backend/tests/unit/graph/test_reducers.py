"""Reducer tests: state merge semantics."""

from app.graph.state import (
    EvidenceRef,
    ExtractedDoc,
    ExtractedField,
    Finding,
    SourceRef,
    merge_by_check_id,
    merge_by_doc_hash,
)


def extracted(sha: str, doc_id: str | None = None, **kw) -> ExtractedDoc:
    return ExtractedDoc(
        doc_id=doc_id or f"doc_{sha[:6]}",
        sha256=sha,
        kind="commercial_invoice",
        fields=[
            ExtractedField(name="total", value="100", confidence=0.9, source=SourceRef(page=1))
        ],
        extraction_model="fast",
        **kw,
    )


def finding(check: str, rule: str, severity: str = "warn", status: str = "open") -> Finding:
    return Finding(
        check_id=check,
        rule_id=rule,
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        summary="s",
        evidence=[EvidenceRef(doc_id="d1", source=SourceRef(page=1))],
    )


class TestMergeByDocHash:
    def test_reextraction_replaces(self):
        old = extracted("aaa")
        new = extracted("aaa", low_confidence=True)
        out = merge_by_doc_hash([old], [new])
        assert len(out) == 1
        assert out[0].low_confidence is True

    def test_distinct_hashes_both_kept_sorted(self):
        out = merge_by_doc_hash([extracted("ccc"), extracted("aaa")], [extracted("bbb")])
        assert [d.sha256 for d in out] == ["aaa", "bbb", "ccc"]

    def test_empty(self):
        assert merge_by_doc_hash([], []) == []

    def test_corrected_upload_supersedes_by_doc_id(self):
        """Same doc slot, new file: the corrected extraction replaces the old."""
        old = extracted("aaa", doc_id="inv-slot", low_confidence=True)
        corrected = extracted("bbb", doc_id="inv-slot")
        out = merge_by_doc_hash([old], [corrected])
        assert [d.sha256 for d in out] == ["bbb"]


class TestMergeByCheckId:
    def test_new_findings_added(self):
        out = merge_by_check_id([], [finding("c1", "r1")])
        assert len(out) == 1

    def test_rerun_replaces_own_findings(self):
        old = finding("c1", "r1", severity="warn")
        new = finding("c1", "r1", severity="block")
        out = merge_by_check_id([old], [new])
        assert len(out) == 1
        assert out[0].severity == "block"

    def test_waived_survives_rerun(self):
        """A human waiver is not erased by a re-run that re-detects the issue."""
        old = finding("c1", "r1", status="waived")
        new = finding("c1", "r1", severity="block", status="open")
        out = merge_by_check_id([old], [new])
        assert len(out) == 1
        assert out[0].status == "waived"

    def test_fixed_replaced_by_resolved_rerun(self):
        old = finding("c1", "r1", status="fixed")
        new = finding("c1", "r1", status="fixed")
        out = merge_by_check_id([old], [new])
        assert len(out) == 1
        assert out[0].status == "fixed"

    def test_sorted_deterministically(self):
        out = merge_by_check_id([], [finding("c2", "r1"), finding("c1", "r2"), finding("c1", "r1")])
        assert [(f.check_id, f.rule_id) for f in out] == [("c1", "r1"), ("c1", "r2"), ("c2", "r1")]
