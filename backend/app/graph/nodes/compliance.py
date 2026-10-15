"""compliance node: runs the deterministic check battery + sanctions screen.

Numbers come from `app.rules.checks` and `app.calc` — the LLM (reasoner) only
writes human explanations for existing findings, never computes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.calc.money import Money
from app.graph.check_inputs import lc_check_inputs
from app.graph.state import DealState, EvidenceRef, ExtractedDoc, Finding, ModelUse
from app.harness.hooks import NodeContext
from app.rules.checks import run_lc_checks


def _doc_of_kind(state: DealState, kind: str) -> ExtractedDoc | None:
    return next((d for d in state.extracted if d.kind == kind), None)


class SanctionsVerdict(BaseModel):
    listed: bool = False
    matched_name: str = ""
    reason: str = ""


async def compliance(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    lc, invoice = lc_check_inputs(state)

    findings: list[Finding] = []

    # 1. deterministic LC consistency battery
    lc_doc = _doc_of_kind(state, "letter_of_credit")
    inv_doc = _doc_of_kind(state, "commercial_invoice")
    schedule_doc = _doc_of_kind(state, "presentation_schedule")
    source_evidence = [
        EvidenceRef(doc_id=doc.doc_id, source=field.source, quote=field.source.snippet)
        for doc in (lc_doc, inv_doc, schedule_doc) if doc is not None
        for field in doc.fields if field.source.snippet
    ]
    for d in run_lc_checks(lc, invoice):
        findings.append(
            Finding(
                check_id="lc-consistency",
                rule_id=d.rule_id,
                severity=d.severity,
                fixable=d.fixable,
                summary=d.summary,
                evidence=source_evidence,
            )
        )

    # 2. sanctions screen — deterministic demo list + (in prod) tool call
    parties = [str(lc.get("beneficiary", "")), str(lc.get("applicant", ""))]
    # DECISION: synthetic sanctions list seeded in seed/rules; demo only
    synthetic_list = {"particle physics ltd", "acme arms llc"}
    for name in parties:
        if name.lower() in synthetic_list:
            evidence = [
                EvidenceRef(doc_id=doc.doc_id, source=field.source, quote=field.source.snippet)
                for doc in state.extracted
                if doc.kind == "letter_of_credit"
                for field in doc.fields
                if field.name in {"beneficiary", "applicant"} and field.source.snippet
            ]
            findings.append(
                Finding(
                    check_id="sanctions-screen",
                    rule_id="sanctions-list-hit",
                    severity="block",
                    fixable=False,
                    summary=f"Party {name!r} matches the (synthetic) sanctions list",
                    evidence=evidence,
                )
            )

    # 3. export VAT refund (deterministic, pure calc; 13% input-VAT assumption
    # comes from the curated rule pack, never from a model)
    total_minor = _parse_minor(lc.get("total_amount") or invoice.get("total_amount"))
    if total_minor is not None:
        from app.calc.vat_refund import VatRefundInput, export_vat_refund

        try:
            r = export_vat_refund(
                VatRefundInput(
                    refund_base=Money(minor=total_minor, currency="CNY"),
                    input_vat=Money(minor=total_minor * 13 // 100, currency="CNY"),
                    refund_rate_bp=1300,
                )
            )
            findings.append(
                Finding(
                    check_id="vat-refund",
                    rule_id="cn-vat-refund-estimate",
                    severity="info",
                    fixable=False,
                    summary=(
                        f"Estimated export VAT refund: {r.refund.to_major_decimal()} CNY"
                        + (" (capped by input VAT)" if r.capped_by_input_vat else "")
                    ),
                    evidence=source_evidence,
                )
            )
        except ValueError as e:
            raise RuntimeError("VAT refund calculation failed for extracted deal values") from e

    # 4. reasoner explanations for human-readable findings (numbers already fixed)
    model_uses: list[ModelUse] = []
    if ctx.llm is not None and findings:
        from pydantic import Field

        class Explainer(BaseModel):
            explanations: list[str] = Field(description="one per finding, plain language")

        system, version = ctx.system_prompt(
            "compliance", state,
            "Explain supplied findings in order. Never add a finding, rule, or number.",
        )
        result = await ctx.llm.complete(
            alias="reasoner",
            system=system + "\n\n" + (
                "Explain compliance findings for a small-business exporter. "
                "Never change numbers; explain them in one sentence each, in order."
            ),
            messages=[
                {
                    "role": "user",
                    "content": "<untrusted>\n"
                    + "\n".join(f"- [{f.severity}] {f.summary}" for f in findings)
                    + "\n</untrusted>",
                }
            ],
            output_model=Explainer,
            node="compliance",
            prompt_version=version,
        )
        if len(result.output.explanations) != len(findings):
            raise ValueError("explainer must return exactly one explanation per finding")
        model_uses.append(result.use)
        for f, expl in zip(findings, result.output.explanations, strict=True):
            f.explanation = expl

    update: dict[str, Any] = {"findings": findings}
    if model_uses:
        update["served_by"] = model_uses
    return update


def _parse_minor(value: object) -> int | None:
    from decimal import Decimal, InvalidOperation

    if value is None:
        return None
    try:
        return int((Decimal(str(value).replace(",", "").strip()) * 100).quantize(Decimal(1)))
    except InvalidOperation:
        return None
