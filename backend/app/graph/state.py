"""DealState and all sub-models — the single source of truth for what flows
through the graph. Everything here is plain Pydantic so state is serializable
into the Postgres checkpointer.

Design invariants (BUILD_PLAN §3.1):
- Documents are referenced by hash only; raw bytes never enter state.
- Every extracted field carries value + confidence + source.
- Money is `Money` (integer minor units + ISO 4217) — never floats.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.calc.finance import FinanceOfferResult
from app.calc.money import Money

DocKind = Literal[
    "letter_of_credit",
    "commercial_invoice",
    "packing_list",
    "bill_of_lading",
    "presentation_schedule",
    "unknown",
]
Severity = Literal["info", "warn", "block"]
FindingStatus = Literal["open", "fixed", "waived"]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


class SourceRef(BaseModel):
    """Where a field came from: page + bbox for PDFs, char span for text."""

    model_config = ConfigDict(frozen=True)

    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    text_span: tuple[int, int] | None = None
    snippet: str = ""  # short quoted text (for the reviewer UI)


class DocRef(BaseModel):
    """Pointer to an uploaded document. Raw bytes stay in object storage."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    deal_id: str
    kind: DocKind = "unknown"
    sha256: str
    filename: str
    mime: str
    size_bytes: int


class ExtractedField(BaseModel):
    name: str
    value: Any = None
    confidence: float = Field(ge=0.0, le=1.0)
    source: SourceRef


class ExtractedDoc(BaseModel):
    doc_id: str
    sha256: str
    kind: DocKind
    fields: list[ExtractedField]
    extraction_model: str  # deployment that produced it
    low_confidence: bool = False

    def get(self, name: str) -> ExtractedField | None:
        return next((f for f in self.fields if f.name == name), None)


# --------------------------------------------------------------------------
# Injection screening
# --------------------------------------------------------------------------


class Flag(BaseModel):
    kind: Literal[
        "instruction_like_phrase",
        "hidden_text",
        "beneficiary_change_language",
        "metadata_anomaly",
        "classifier_hit",
    ]
    severity: Severity
    doc_id: str
    evidence: list[SourceRef] = []
    detail: str


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


class CheckPlan(BaseModel):
    plan_id: str
    chosen_skills: list[str] = []
    checks: list[str] = []  # check ids the plan will run
    rationale: str = ""


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    source: SourceRef
    quote: str = ""


class Finding(BaseModel):
    check_id: str
    rule_id: str
    severity: Severity
    status: FindingStatus = "open"
    fixable: bool = False
    summary: str
    explanation: str = ""
    evidence: list[EvidenceRef] = []


def merge_by_doc_hash(existing: list[ExtractedDoc], new: list[ExtractedDoc]) -> list[ExtractedDoc]:
    """Reducer: one extraction per document slot. A re-extraction replaces the
    entry with the same sha256 (idempotent re-read) OR the same doc_id
    (corrected upload supersedes the flawed original)."""
    merged: dict[str, ExtractedDoc] = {}
    positions: dict[str, str] = {}  # doc_id -> sha key
    for d in existing:
        merged[d.sha256] = d
        positions[d.doc_id] = d.sha256
    for d in new:
        old_sha = positions.get(d.doc_id)
        if old_sha is not None and old_sha != d.sha256:
            merged.pop(old_sha, None)  # corrected version replaces the old read
        merged[d.sha256] = d
        positions[d.doc_id] = d.sha256
    return sorted(merged.values(), key=lambda d: d.sha256)


def merge_by_check_id(existing: list[Finding], new: list[Finding]) -> list[Finding]:
    """Reducer: findings merge by (check_id, rule_id); a re-run replaces its own
    findings, and 'fixed'/'waived' statuses survive re-runs of the same check
    only when the new finding is resolved."""

    def key(f: Finding) -> tuple[str, str]:
        return (f.check_id, f.rule_id)

    merged: dict[tuple[str, str], Finding] = {key(f): f for f in existing}
    for f in new:
        old = merged.get(key(f))
        # keep human decisions: an old waived finding is only replaced by a
        # re-detected one if the new run still reports it as open
        if old is not None and old.status in ("fixed", "waived") and f.status == "open":
            continue
        merged[key(f)] = f
    return sorted(merged.values(), key=key)


def merge_flags(existing: list[Flag], new: list[Flag]) -> list[Flag]:
    """Reducer for injection flags: dedupe by (doc_id, kind, detail)."""

    def key(f: Flag) -> tuple[str, str, str]:
        return (f.doc_id, f.kind, f.detail)

    merged: dict[tuple[str, str, str], Flag] = {key(f): f for f in existing}
    for f in new:
        merged[key(f)] = f
    return sorted(merged.values(), key=key)


def merge_doc_refs(existing: list[DocRef], new: list[DocRef]) -> list[DocRef]:
    merged = {d.doc_id: d for d in existing}
    merged.update({d.doc_id: d for d in new})
    return sorted(merged.values(), key=lambda d: d.doc_id)


def merge_last_wins(existing: str | None, new: str | None) -> str | None:
    """Reducer for scalar operational fields written by parallel branches:
    last write wins (a failure is a failure)."""
    return new if new is not None else existing


def merge_model_uses(existing: list[ModelUse], new: list[ModelUse]) -> list[ModelUse]:
    return [*existing, *new]


# --------------------------------------------------------------------------
# FX / cash / finance (state mirrors of calc outputs)
# --------------------------------------------------------------------------


class FxOption(BaseModel):
    """One FX route evaluated for this deal (state-safe copy of calc output)."""

    route_id: str
    provider: str
    synthetic: bool = True
    sell_currency: str
    buy_currency: str
    amount_minor: int
    net_minor: int
    effective_rate_scaled: int
    spread_bp: int
    fee_minor: int


class CashEventState(BaseModel):
    day: int
    amount_minor: int
    currency: str
    label: str
    source: str = "deal"


class CashProjectionState(BaseModel):
    currency: str
    opening_balance_minor: int
    daily_balance_minor: list[int]
    min_balance_minor: int
    min_balance_day: int
    days_below_zero: int
    events: list[CashEventState]


class FinanceOfferState(BaseModel):
    """What the approval screen shows for the financing option."""

    provider: str
    face: Money
    advance: Money
    total_cost: Money
    net_proceeds: Money
    effective_cost_bp_annual: int
    days_to_maturity: int
    synthetic: bool = True

    @classmethod
    def from_result(
        cls, provider: str, days: int, inp_face: Money, r: FinanceOfferResult
    ) -> FinanceOfferState:
        return cls(
            provider=provider,
            face=inp_face,
            advance=r.advance,
            total_cost=r.total_cost,
            net_proceeds=r.net_proceeds,
            effective_cost_bp_annual=r.effective_cost_bp_annual,
            days_to_maturity=days,
        )


# --------------------------------------------------------------------------
# Policy / approval / execution
# --------------------------------------------------------------------------


class PolicyRuleResult(BaseModel):
    rule: str
    allowed: bool
    detail: str


class PolicyDecision(BaseModel):
    decision: Literal["allow", "deny", "escalate"]
    engine: str  # "cedar" | "fallback"
    rules: list[PolicyRuleResult] = []
    reason: str = ""


class SignedApproval(BaseModel):
    deal_hash: str  # canonical hash of exactly what the approval screen rendered
    approver_id: str
    method: Literal["webauthn_passkey", "wechat_soter", "pin_otp"]
    signature_b64: str
    signed_at: str  # ISO 8601 UTC
    nonce: str


class Receipt(BaseModel):
    receipt_id: str
    deal_id: str
    payout_ref: str
    amount: Money
    anchored_hash: str | None = None
    anchor_tx: str | None = None
    executed_at: str


class ModelUse(BaseModel):
    """One model call: which deployment served it and what it cost."""

    node: str
    alias: str
    deployment: str
    prompt_tokens: int
    completion_tokens: int
    cost_minor: int = 0  # USD minor units, from LiteLLM usage data
    degraded: bool = False  # served by a fallback deployment
    prompt_version: str = ""


# --------------------------------------------------------------------------
# Root state
# --------------------------------------------------------------------------


class DealState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    deal_id: str
    tenant_id: str
    documents: Annotated[list[DocRef], merge_doc_refs] = []
    extracted: Annotated[list[ExtractedDoc], merge_by_doc_hash] = []
    injection_flags: Annotated[list[Flag], merge_flags] = []
    check_plan: CheckPlan | None = None
    findings: Annotated[list[Finding], merge_by_check_id] = []
    fx_options: list[FxOption] = []
    cash_projection: CashProjectionState | None = None
    verified: list[Finding] = []
    amendment_draft: str | None = None
    resolve_attempts: int = 0
    finance_offer: FinanceOfferState | None = None
    policy: PolicyDecision | None = None
    approval: SignedApproval | None = None
    receipt: Receipt | None = None
    report_summary: str | None = None
    served_by: Annotated[list[ModelUse], merge_model_uses] = []
    # operational field: set by the node hooks on any failure; routers check it
    # first and route to escalate (fail closed). Never set by node code itself.
    # Reducer: parallel branches (compliance|fx|cashflow) may fail in the same
    # step — last write wins.
    fatal_error: Annotated[str | None, merge_last_wins] = None
    # set by the escalate node; the report/UX reads it
    escalation_reason: Annotated[str | None, merge_last_wins] = None
    # Send() carrier for extract_doc fan-out (never merged from node updates)
    pending_doc: DocRef | None = None

    # --- derived helpers (never serialized differently) ---

    def has_block_findings(self) -> bool:
        return any(f.severity == "block" and f.status == "open" for f in self.findings)

    def open_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "open"]

    def blocked_by_injection(self) -> bool:
        return any(f.severity == "block" for f in self.injection_flags)


class ResumePayload(BaseModel):
    """What a human sends back when resuming an interrupt."""

    action: Literal["approve", "reject", "corrected_document", "retry", "resolve"]
    approver_id: str | None = None
    approval: SignedApproval | None = None
    note: str = ""
    waiver: Waiver | None = None


class Waiver(BaseModel):
    finding_check_id: str
    named_human: str
    reason: str = Field(min_length=8)
