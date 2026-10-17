"""Deterministic LC document checks (UCP 600 style consistency).

Pure functions over extracted fields: they produce raw discrepancies; nodes
attach evidence and the LLM only writes explanations. Rule ids reference
curated seed rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.calc.money import Money

# field names as produced by extract_doc
F_TOTAL = "total_amount"
F_CURRENCY = "currency"
F_GOODS = "goods_description"
F_QUANTITY = "quantity"
F_SHIP_DATE = "shipment_date"
F_LC_EXPIRY = "expiry_date"
F_BENEFICIARY = "beneficiary"
F_APPLICANT = "applicant"
F_LC_AMOUNT = "lc_amount"
F_LATEST_SHIPMENT = "latest_shipment_date"
F_PRESENTATION = "presentation_date"

# UCP 600 Art. 14(c): presentation within 21 calendar days after shipment
PRESENTATION_DAYS = 21


@dataclass(frozen=True)
class Discrepancy:
    rule_id: str
    severity: str  # info | warn | block
    fixable: bool
    summary: str


def _parse_amount(value: object) -> int | None:
    """Best-effort parse of a human-typed amount to minor units (no floats for
    storage: parse via Decimal)."""
    from decimal import Decimal, InvalidOperation

    if value is None:
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return int((d * 100).quantize(Decimal(1)))


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def check_amount_match(lc_amount: Money | None, invoice_amount: Money | None) -> Discrepancy | None:
    """UCP 600 Art. 18(b): invoice must not exceed LC amount."""
    if lc_amount is None or invoice_amount is None:
        return None
    if invoice_amount.currency != lc_amount.currency:
        return Discrepancy(
            "lc-currency-mismatch",
            "block",
            True,
            f"Currency mismatch: LC in {lc_amount.currency}, invoice in {invoice_amount.currency}",
        )
    if invoice_amount.minor > lc_amount.minor:
        return Discrepancy(
            "lc-invoice-exceeds-lc",
            "block",
            True,
            f"Invoice {invoice_amount.to_major_decimal()} {invoice_amount.currency} exceeds "
            f"LC {lc_amount.to_major_decimal()} {lc_amount.currency}",
        )
    return None


def check_expiry_after_shipment(
    shipment_date: str | None, expiry_date: str | None
) -> Discrepancy | None:
    if not shipment_date or not expiry_date:
        return None

    def parse(v: str) -> date | None:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                from datetime import datetime as dt

                return dt.strptime(v.strip()[:19], fmt).date()
            except ValueError:
                continue
        return None

    ship, exp = parse(shipment_date), parse(expiry_date)
    if ship is None or exp is None:
        return Discrepancy(
            "doc-date-unparseable", "warn", False, "Shipment or expiry date could not be parsed"
        )
    if ship > exp:
        # not curable by a corrected document — needs an LC expiry amendment
        # from the applicant, so it escalates rather than looping resolve
        return Discrepancy(
            "ucp600-shipment-after-expiry",
            "block",
            False,
            f"Shipment {ship} is after LC expiry {exp}",
        )
    return None


def _parse_date(value: str) -> date | None:
    from datetime import datetime as dt

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.strptime(value.strip()[:19], fmt).date()
        except ValueError:
            continue
    return None


def check_latest_shipment(
    shipment_date: str | None, latest_shipment: str | None
) -> Discrepancy | None:
    """Shipment must not be dated after the credit's latest shipment date.

    Not curable by a corrected document (the bill of lading is a fact); it needs
    an LC amendment from the applicant, so it escalates instead of looping.
    """
    if not shipment_date or not latest_shipment:
        return None
    ship, latest = _parse_date(shipment_date), _parse_date(latest_shipment)
    if ship is None or latest is None:
        return Discrepancy(
            "doc-date-unparseable", "warn", False, "Shipment or latest shipment date unparseable"
        )
    if ship > latest:
        return Discrepancy(
            "lc-late-shipment",
            "block",
            False,
            f"Shipment {ship} is after the LC latest shipment date {latest}",
        )
    return None


def check_presentation_period(
    shipment_date: str | None, presentation_date: str | None, expiry_date: str | None
) -> Discrepancy | None:
    """UCP 600 Art. 14(c): within 21 calendar days of shipment, never after expiry."""
    if not shipment_date or not presentation_date:
        return None
    ship, pres = _parse_date(shipment_date), _parse_date(presentation_date)
    if ship is None or pres is None:
        return Discrepancy(
            "doc-date-unparseable", "warn", False, "Shipment or presentation date unparseable"
        )
    expiry = _parse_date(expiry_date) if expiry_date else None
    if expiry is not None and pres > expiry:
        return Discrepancy(
            "ucp-presentation-after-expiry",
            "block",
            False,
            f"Presentation {pres} is after LC expiry {expiry}",
        )
    if (pres - ship).days > PRESENTATION_DAYS:
        return Discrepancy(
            "ucp-late-presentation",
            "block",
            False,
            f"Presentation {pres} is more than {PRESENTATION_DAYS} days after shipment {ship}",
        )
    return None


def check_goods_description(lc_goods: str | None, invoice_goods: str | None) -> Discrepancy | None:
    if not lc_goods or not invoice_goods:
        return None
    # conservative containment check on normalised text (LLM explanation only)
    if _norm(lc_goods)[:80] not in _norm(invoice_goods) and _norm(invoice_goods)[:80] not in _norm(
        lc_goods
    ):
        return Discrepancy(
            "ucp600-goods-description",
            "warn",
            True,
            "Goods description differs between LC and invoice",
        )
    return None


def check_quantity(lc_qty: str | None, inv_qty: str | None) -> Discrepancy | None:
    if not lc_qty or not inv_qty:
        return None
    if _norm(lc_qty) != _norm(inv_qty):
        return Discrepancy(
            "doc-quantity-mismatch",
            "block",
            True,
            f"Quantity mismatch: LC {lc_qty!r} vs invoice {inv_qty!r}",
        )
    return None


def check_beneficiary(
    lc_beneficiary: str | None, inv_beneficiary: str | None
) -> Discrepancy | None:
    if not lc_beneficiary or not inv_beneficiary:
        return None
    if _norm(lc_beneficiary) != _norm(inv_beneficiary):
        return Discrepancy(
            "doc-beneficiary-mismatch",
            "block",
            False,
            f"Beneficiary mismatch: LC {lc_beneficiary!r} vs invoice {inv_beneficiary!r}",
        )
    return None


def run_lc_checks(lc: dict[str, object], invoice: dict[str, object]) -> list[Discrepancy]:
    """Run the deterministic battery over two extracted-field dicts."""
    out: list[Discrepancy] = []

    lc_amount = None
    inv_amount = None
    lc_minor = _parse_amount(lc.get(F_LC_AMOUNT) or lc.get(F_TOTAL))
    inv_minor = _parse_amount(invoice.get(F_TOTAL))
    cur = str(lc.get(F_CURRENCY) or invoice.get(F_CURRENCY) or "USD").upper()
    if lc_minor is not None:
        lc_amount = Money(minor=lc_minor, currency=cur)
    if inv_minor is not None:
        inv_amount = Money(minor=inv_minor, currency=cur)

    for check, args in [
        (check_amount_match, (lc_amount, inv_amount)),
        (check_expiry_after_shipment, (invoice.get(F_SHIP_DATE), lc.get(F_LC_EXPIRY))),
        (check_latest_shipment, (invoice.get(F_SHIP_DATE), lc.get(F_LATEST_SHIPMENT))),
        (
            check_presentation_period,
            (invoice.get(F_SHIP_DATE), invoice.get(F_PRESENTATION), lc.get(F_LC_EXPIRY)),
        ),
        (check_goods_description, (lc.get(F_GOODS), invoice.get(F_GOODS))),
        (check_quantity, (lc.get(F_QUANTITY), invoice.get(F_QUANTITY))),
        (check_beneficiary, (lc.get(F_BENEFICIARY), invoice.get(F_BENEFICIARY))),
    ]:
        d = check(*args)  # type: ignore[operator]
        if d is not None:
            out.append(d)
    return out
