"""verify node: re-derives each finding from source evidence (BUILD_PLAN M5).

Never trusts other agents' prose: for each finding the node re-reads the source
documents (deterministic re-computation where a check is computable) and asks
`reasoner` only to judge *explanations* against the evidence, with
`allow_degraded=False` — a fallback-tier model may not adjudicate.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.graph.check_inputs import lc_check_inputs
from app.graph.state import DealState, Finding, ModelUse
from app.harness.document_parsing import full_text, parse_pdf_spans
from app.harness.hooks import NodeContext
from app.harness.tools.registry import Tool, ToolRegistry
from app.rules.checks import run_lc_checks

# check ids whose findings are pure-calculator outputs (see DECISION in verify())
CALC_CHECK_IDS = frozenset({"vat-refund"})


class Verdict(BaseModel):
    check_id: str
    rule_id: str = ""
    upheld: bool | None = None
    needs_evidence: bool = False
    reason: str


class VerifyOutput(BaseModel):
    verdicts: list[Verdict]


def _verdicts_by_finding(verdicts: list[Verdict]) -> dict[tuple[str, str], Verdict]:
    """Index verdicts by the same composite key used by the finding reducer."""
    return {(verdict.check_id, verdict.rule_id): verdict for verdict in verdicts}


class SourceInput(BaseModel):
    deal_id: str
    tenant_id: str
    doc_id: str


class SourceOutput(BaseModel):
    text: str


def _recompute_check_ids(state: DealState) -> set[str]:
    """Which finding rule-ids reproduce under the deterministic battery."""
    lc, inv = lc_check_inputs(state)
    return {d.rule_id for d in run_lc_checks(lc, inv)}


async def verify(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    reproducible = _recompute_check_ids(state)
    verdicts: list[Verdict] = []
    verified: list[Finding] = []
    updated: list[Finding] = []
    model_uses: list[ModelUse] = []
    model_candidates: list[tuple[Finding, str]] = []
    source_registry = ToolRegistry(audit_sink=ctx.audit)

    def read_source(raw_args: BaseModel) -> BaseModel:
        args = SourceInput.model_validate(raw_args)
        doc = next((d for d in state.documents if d.doc_id == args.doc_id), None)
        if doc is None or doc.deal_id != args.deal_id or doc.mime != "application/pdf":
            raise ValueError("source document is missing or unsupported")
        return SourceOutput(text=full_text(parse_pdf_spans(ctx.docs.get(doc.sha256))))

    source_registry.register(
        Tool(
            name="read_source_doc",
            description="Read original PDF text for verification",
            fn=read_source,
            input_model=SourceInput,
            output_model=SourceOutput,
            side_effect="read",
            allowed_nodes=frozenset({"verify"}),
            llm_callable=True,
        )
    )

    for f in state.findings:
        if f.status != "open":
            updated.append(f)
            continue
        if f.check_id == "lc-consistency" and f.fixable and f.rule_id not in reproducible:
            # DECISION: a finding the deterministic battery no longer reproduces
            # (e.g. after a corrected upload) is closed without grounding; its
            # old evidence quotes legitimately vanish from the replaced document.
            verdicts.append(
                Verdict(
                    check_id=f.check_id,
                    rule_id=f.rule_id,
                    upheld=False,
                    reason="not reproducible from source documents",
                )
            )
            updated.append(
                f.model_copy(
                    update={
                        "status": "fixed",
                        "explanation": "not reproducible after document correction",
                    }
                )
            )
            continue
        sources: list[str] = []
        grounded = bool(f.evidence) and ctx.docs is not None
        for ref in f.evidence:
            if not ref.quote:
                grounded = False
                continue
            try:
                source = source_registry.call(
                    "verify",
                    "read_source_doc",
                    SourceInput(
                        deal_id=state.deal_id,
                        tenant_id=state.tenant_id,
                        doc_id=ref.doc_id,
                    ),
                )
            except FileNotFoundError:
                grounded = False
                continue
            except Exception:
                grounded = False
                continue
            if not isinstance(source, SourceOutput):
                grounded = False
                continue
            source_text = source.text
            if ref.quote not in source_text:
                grounded = False
            else:
                sources.append(ref.quote)
        if not grounded:
            updated.append(
                f.model_copy(
                    update={
                        "explanation": "verification failed: source evidence missing or ungrounded"
                    }
                )
            )
            continue
        # Non-fixable trade facts cannot be cured by an upload or dismissed by
        # a model. Preserve a grounded finding so routing escalates it.
        if not f.fixable:
            verified.append(f)
            updated.append(f)
            continue
        if f.check_id == "lc-consistency":
            # adjudicated by re-computation, never by a model
            upheld = f.rule_id in reproducible
            verdicts.append(
                Verdict(
                    check_id=f.check_id,
                    rule_id=f.rule_id,
                    upheld=upheld,
                    reason="recomputed from source documents"
                    if upheld
                    else "not reproducible from source documents",
                )
            )
            if upheld:
                verified.append(f)
                updated.append(f)
            else:
                # the corrected documents no longer show this discrepancy
                resolved = f.model_copy(
                    update={
                        "status": "fixed",
                        "explanation": "not reproducible after document correction",
                    }
                )
                updated.append(resolved)
            continue

        if f.check_id in CALC_CHECK_IDS:
            # DECISION: findings whose numbers come from a pure calc/ function are
            # upheld once their evidence is grounded in the source PDF; a model
            # never adjudicates (or produces) a calculator result.
            verdicts.append(
                Verdict(
                    check_id=f.check_id,
                    rule_id=f.rule_id,
                    upheld=True,
                    reason="deterministic calculator output",
                )
            )
            verified.append(f)
            updated.append(f)
            continue

        # Grounding is complete; defer all non-computable findings to one call.
        model_candidates.append((f, "\n".join(sources)))

    if model_candidates:
        assert ctx.llm is not None
        system, version = ctx.system_prompt(
            "verify",
            state,
            "Insufficient source evidence must return needs_evidence and never clear a finding.",
        )
        entries = [
            {
                "check_id": f.check_id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "summary": f.summary,
                "evidence": evidence,
            }
            for f, evidence in model_candidates
        ]
        result = await ctx.llm.complete(
            alias="reasoner",
            allow_degraded=False,
            system=system
            + "\n\nJudge every finding independently using only its supplied evidence. "
            "Return exactly one verdict per (check_id, rule_id). Insufficient evidence must set "
            "needs_evidence=true; never clear a finding based on missing information.",
            messages=[{"role": "user", "content": f"<untrusted>\n{entries}\n</untrusted>"}],
            output_model=VerifyOutput,
            node="verify",
            prompt_version=version,
        )
        model_uses.append(result.use)
        verdict_map = _verdicts_by_finding(result.output.verdicts)
        for f, _ in model_candidates:
            v = verdict_map.get((f.check_id, f.rule_id))
            if v is None:
                v = Verdict(
                    check_id=f.check_id,
                    rule_id=f.rule_id,
                    needs_evidence=True,
                    reason="no verdict returned",
                )
            verdicts.append(v)
            if v.upheld is True and not v.needs_evidence:
                verified.append(f)
                updated.append(f)
            elif v.upheld is False and not v.needs_evidence:
                updated.append(
                    f.model_copy(
                        update={
                            "status": "fixed",
                            "explanation": f"dismissed at verification: {v.reason[:200]}",
                        }
                    )
                )
            else:
                updated.append(
                    f.model_copy(
                        update={"explanation": "verification inconclusive; escalation required"}
                    )
                )

    return {"verified": verified, "findings": updated, "served_by": model_uses}
