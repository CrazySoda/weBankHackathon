"""Router tests: every edge decision is pure and deterministic."""

from app.graph.routers import (
    after_approval,
    after_policy,
    after_screen,
    after_verify,
    fan_out_docs,
)
from app.graph.state import (
    DealState,
    DocRef,
    ExtractedDoc,
    ExtractedField,
    Finding,
    Flag,
    PolicyDecision,
    SignedApproval,
    SourceRef,
)


def state(**kw) -> DealState:
    return DealState(deal_id="d1", tenant_id="t1", **kw)


def doc(sha: str) -> DocRef:
    return DocRef(
        doc_id=f"doc_{sha[:6]}",
        deal_id="d1",
        sha256=sha,
        filename="f.pdf",
        mime="application/pdf",
        size_bytes=10,
    )


def extracted(sha: str) -> ExtractedDoc:
    return ExtractedDoc(
        doc_id=f"doc_{sha[:6]}",
        sha256=sha,
        kind="commercial_invoice",
        fields=[ExtractedField(name="x", value="1", confidence=0.9, source=SourceRef(page=1))],
        extraction_model="fast",
    )


def finding(severity: str, fixable: bool, status: str = "open") -> Finding:
    return Finding(
        check_id="c1",
        rule_id="r1",
        severity=severity,  # type: ignore[arg-type]
        fixable=fixable,
        status=status,  # type: ignore[arg-type]
        summary="s",
    )


class TestFanOutDocs:
    def test_one_send_per_unextracted_doc(self):
        s = state(documents=[doc("a"), doc("b")])
        sends = fan_out_docs(s)
        assert len(sends) == 2
        assert {send.arg["pending_doc"]["sha256"] for send in sends} == {"a", "b"}

    def test_skips_already_extracted(self):
        s = state(documents=[doc("a"), doc("b")], extracted=[extracted("a")])
        sends = fan_out_docs(s)
        assert [send.arg["pending_doc"]["sha256"] for send in sends] == ["b"]

    def test_no_docs_no_sends(self):
        assert fan_out_docs(state()) == []


class TestAfterScreen:
    def test_clean_goes_to_plan(self):
        assert after_screen(state()) == "plan"

    def test_block_flag_escalates(self):
        s = state(
            injection_flags=[
                Flag(kind="hidden_text", severity="block", doc_id="d1", detail="white text")
            ]
        )
        assert after_screen(s) == "escalate"

    def test_warn_flag_continues(self):
        s = state(
            injection_flags=[
                Flag(
                    kind="metadata_anomaly",
                    severity="warn",
                    doc_id="d1",
                    detail="odd producer field",
                )
            ]
        )
        assert after_screen(s) == "plan"

    def test_fatal_escalates(self):
        assert after_screen(state(fatal_error="x")) == "escalate"


class TestAfterVerify:
    def test_no_blocks_goes_to_credit(self):
        s = state(findings=[finding("info", False), finding("warn", True)])
        assert after_verify(s) == "credit_offer"

    def test_fixable_block_goes_to_resolve(self):
        s = state(findings=[finding("block", fixable=True)])
        assert after_verify(s) == "resolve_exception"

    def test_unfixable_block_escalates(self):
        s = state(findings=[finding("block", fixable=False)])
        assert after_verify(s) == "escalate"

    def test_second_retry_escalates(self):
        s = state(resolve_attempts=1, findings=[finding("block", fixable=True)])
        assert after_verify(s) == "escalate"

    def test_fatal_escalates_even_without_findings(self):
        assert after_verify(state(fatal_error="x")) == "escalate"


class TestAfterPolicy:
    def test_allow_goes_to_approval(self):
        from app.graph.state import PolicyRuleResult

        s = state(
            policy=PolicyDecision(
                decision="allow",
                engine="cedar",
                rules=[PolicyRuleResult(rule="amount_cap", allowed=True, detail="ok")],
            )
        )
        assert after_policy(s) == "human_approval"

    def test_deny_escalates(self):
        s = state(policy=PolicyDecision(decision="deny", engine="cedar"))
        assert after_policy(s) == "escalate"

    def test_missing_policy_escalates(self):
        assert after_policy(state()) == "escalate"


class TestAfterApproval:
    def test_approved_executes(self):
        s = state(
            approval=SignedApproval(
                deal_hash="h",
                approver_id="u",
                method="webauthn_passkey",
                signature_b64="sig",
                signed_at="2026-01-01T00:00:00+00:00",
                nonce="n",
            )
        )
        assert after_approval(s) == "execute"

    def test_rejected_reports(self):
        assert after_approval(state()) == "report"
