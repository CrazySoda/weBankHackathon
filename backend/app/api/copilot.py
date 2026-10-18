"""Deal copilot: read-only questions about one deal (review console).

A tool-less model call on the `fast` alias. The server builds the deal record
the model sees (every amount pre-formatted from integer minor units here, never
by the model), the person's question and earlier turns are wrapped in
``<untrusted>``, and the answer is checked before it leaves:

- instruction-like questions are declined without a model call;
- any number in the answer that is not in the deal record fails the answer
  closed (``CopilotUnverified``) — the model may quote figures, never derive them;
- ``finding_ids`` / ``card`` are clamped to what exists on the deal.

Usage is capped per deal and kept apart from the pipeline budget, so chatting
can never trip a deal's kill switch (DECISIONS #25).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.calc.money import Money, minor_exponent
from app.graph.nodes.injection_screen import INSTRUCTION_PATTERNS
from app.graph.state import DealState, ModelUse
from app.harness.prompts.loader import load_prompt
from app.harness.skills.loader import load_manifests, render_skills_section
from pydantic import BaseModel, Field

NODE = "copilot"
RATE_SCALE = 1_000_000  # matches calc.fx effective_rate_scaled
MAX_HISTORY_TURNS = 8
FREE_NUMBERS = {str(n) for n in range(11)}  # list positions / small counts

CardKind = Literal["findings", "fx", "cash", "documents", "none"]


class CopilotTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[CopilotTurn] = Field(default=[], max_length=40)
    focus_check_id: str | None = Field(default=None, max_length=200)


class CopilotAnswer(BaseModel):
    """Model output contract (prompts/copilot.md)."""

    answer: str
    card: CardKind = "none"
    finding_ids: list[str] = []
    follow_ups: list[str] = []


class CopilotUnverified(RuntimeError):
    """The answer quoted a number that is not in the deal record."""


class CopilotLimit(RuntimeError):
    """The deal's copilot allowance is used up."""


# -- deal record -----------------------------------------------------------


def fmt_money(minor: int, currency: str) -> str:
    try:
        major = Money(minor=minor, currency=currency).to_major_decimal()
    except ValueError:
        return f"{minor} {currency} minor units"
    return f"{currency} {major:,.{minor_exponent(currency)}f}"


def fmt_rate(scaled: int) -> str:
    rate = (Decimal(scaled) / RATE_SCALE).normalize()
    return f"{rate:f}"


@lru_cache(maxsize=1)
def _rule_summaries() -> dict[str, str]:
    from app.rules.loader import load_rule_pack

    try:
        rows = load_rule_pack()
    except Exception:
        return {}
    return {r.rule_id: str(r.content.get("_meta", {}).get("summary", "")) for r in rows}


def deal_record(state: DealState) -> dict[str, Any]:
    """Everything the copilot may say about the deal, amounts already formatted."""
    rules = _rule_summaries()
    open_findings = [f for f in state.findings if f.status == "open"]
    record: dict[str, Any] = {
        "deal_id": state.deal_id,
        "documents": [
            {"doc_id": d.doc_id, "filename": d.filename, "kind": d.kind} for d in state.documents
        ],
        "document_count": len(state.documents),
        "extraction_count": len(state.extracted),
        "open_finding_count": len(open_findings),
        "blocking_finding_count": sum(1 for f in open_findings if f.severity == "block"),
        "findings": [
            {
                "check_id": f.check_id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "status": f.status,
                "fixable": f.fixable,
                "summary": f.summary,
                "explanation": f.explanation,
                "rule_summary": rules.get(f.rule_id, ""),
            }
            for f in state.findings
        ],
        "injection_flags": [
            {"kind": fl.kind, "severity": fl.severity, "doc_id": fl.doc_id}
            for fl in state.injection_flags
        ],
        "fx_routes": [
            {
                "route_id": o.route_id,
                "provider": o.provider,
                "synthetic": o.synthetic,
                "sell": fmt_money(o.amount_minor, o.sell_currency),
                "net_received": fmt_money(o.net_minor, o.buy_currency),
                "effective_rate": fmt_rate(o.effective_rate_scaled),
                "spread_bp": o.spread_bp,
                "fee": fmt_money(o.fee_minor, o.fee_currency or o.sell_currency),
            }
            for o in state.fx_options
        ],
        "policy": (
            {"decision": state.policy.decision, "reason": state.policy.reason}
            if state.policy
            else None
        ),
        "escalation_reason": state.escalation_reason,
        "approved": state.approval is not None,
        "paid_out": state.receipt is not None,
        "report_summary": state.report_summary,
    }
    if state.fx_options:
        best = max(state.fx_options, key=lambda o: o.net_minor)
        record["best_net_fx_route"] = best.route_id
    cp = state.cash_projection
    if cp is not None:
        record["cash_projection"] = {
            "assumptions": "illustrative; zero opening cash, deposit on day 0, LC at maturity",
            "horizon_days": max(0, len(cp.daily_balance_minor) - 1),
            "lowest_balance": fmt_money(cp.min_balance_minor, cp.currency),
            "lowest_balance_day": cp.min_balance_day,
            "days_below_zero": cp.days_below_zero,
            "events": [
                {"day": e.day, "label": e.label, "amount": fmt_money(e.amount_minor, e.currency)}
                for e in cp.events
            ],
        }
    fo = state.finance_offer
    if fo is not None:
        record["finance_offer"] = {
            "provider": fo.provider,
            "face": fmt_money(fo.face.minor, fo.face.currency),
            "advance": fmt_money(fo.advance.minor, fo.advance.currency),
            "total_cost": fmt_money(fo.total_cost.minor, fo.total_cost.currency),
            "net_proceeds": fmt_money(fo.net_proceeds.minor, fo.net_proceeds.currency),
            "effective_cost_bp_annual": fo.effective_cost_bp_annual,
            "days_to_maturity": fo.days_to_maturity,
        }
    return record


def extracted_fields(state: DealState) -> list[dict[str, Any]]:
    """Values read out of the documents: untrusted, kept in their own block."""
    return [
        {"kind": d.kind, "fields": {f.name: f.value for f in d.fields}}
        for d in state.current_extracted
    ]


# -- checks ------------------------------------------------------------------

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm_number(token: str) -> str:
    n = token.replace(",", "")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_norm_number(t) for t in _NUMBER.findall(text)}


def unverified_numbers(answer: str, *sources: str) -> set[str]:
    allowed = set(FREE_NUMBERS)
    for s in sources:
        allowed |= numbers_in(s)
    return numbers_in(answer) - allowed


def screened(question: str) -> bool:
    return any(re.search(p, question, re.IGNORECASE) for p in INSTRUCTION_PATTERNS)


def system_prompt() -> tuple[str, str]:
    prompts = Path(__file__).resolve().parents[2] / "prompts"
    skills = Path(__file__).resolve().parents[2] / "skills"
    text = load_prompt(prompts, NODE).replace(
        "{{skills}}", render_skills_section(load_manifests(skills), NODE, [])
    )
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# -- service -------------------------------------------------------------------

DECLINED = (
    "I can only answer questions about this deal's record. I can't follow instructions to "
    "change how I work or take actions."
)


@dataclass
class CopilotReply:
    answer: str
    card: CardKind
    finding_ids: list[str]
    follow_ups: list[str]
    screened: bool = False
    use: ModelUse | None = None
    prompt_version: str = ""


@dataclass
class CopilotService:
    max_turns: int
    max_tokens: int
    turns: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)

    async def ask(self, llm: Any, state: DealState, req: CopilotRequest) -> CopilotReply:
        deal_id = state.deal_id
        if (
            self.turns.get(deal_id, 0) >= self.max_turns
            or self.tokens.get(deal_id, 0) >= self.max_tokens
        ):
            raise CopilotLimit(deal_id)
        if screened(req.question):
            return CopilotReply(DECLINED, "none", [], [], screened=True)

        record = json.dumps(deal_record(state), ensure_ascii=False, default=str)
        extracted = json.dumps(extracted_fields(state), ensure_ascii=False, default=str)
        history = "\n".join(
            f"{t.role}: {t.text}" for t in req.history[-MAX_HISTORY_TURNS:] if t.text.strip()
        )
        focus = (
            f"\nThe person is asking about finding check_id={req.focus_check_id!r}."
            if req.focus_check_id
            else ""
        )
        content = (
            f"<deal_record>\n{record}\n</deal_record>\n\n"
            "Values read from the uploaded documents:\n"
            f"<untrusted>\n{extracted}\n</untrusted>\n\n"
            + (
                f"Earlier conversation:\n<untrusted>\n{history}\n</untrusted>\n\n"
                if history
                else ""
            )
            + f"Question:{focus}\n<untrusted>\n{req.question}\n</untrusted>"
        )
        system, version = system_prompt()
        result = await llm.complete(
            alias="fast",
            system=system,
            messages=[{"role": "user", "content": content}],
            output_model=CopilotAnswer,
            node=NODE,
            prompt_version=version,
            temperature=0.2,
            max_tokens=1500,
        )
        use: ModelUse = result.use
        self.turns[deal_id] = self.turns.get(deal_id, 0) + 1
        self.tokens[deal_id] = (
            self.tokens.get(deal_id, 0) + use.prompt_tokens + use.completion_tokens
        )

        out: CopilotAnswer = result.output
        answer = out.answer.strip()[:2500]
        # history is the person's own text, so they may refer back to their numbers
        bad = unverified_numbers(answer, record, extracted, req.question)
        if bad:
            raise CopilotUnverified(", ".join(sorted(bad)[:5]))
        known = {f.check_id for f in state.findings}
        card: CardKind = out.card
        if (card == "fx" and not state.fx_options) or (
            card == "cash" and state.cash_projection is None
        ):
            card = "none"
        return CopilotReply(
            answer=answer,
            card=card,
            finding_ids=[i for i in out.finding_ids if i in known][:6],
            follow_ups=[q.strip()[:120] for q in out.follow_ups if q.strip()][:3],
            use=use,
            prompt_version=version,
        )
