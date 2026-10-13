"""Export VAT refund (China export-tax-rebate model).

Model (simplified but faithful to the mechanism):
- refund_base   : FOB invoice value in CNY minor units.
- input_vat     : input VAT actually paid on procurement, CNY minor units.
- refund_rate_bp: published rebate rate in basis points (e.g. 1300 = 13.00%).

refund = min(round_half_up(refund_base * refund_rate_bp / 10_000), input_vat)

The refund can never exceed the input VAT actually suffered — overrebating is a
classic fraud vector, so the calculator caps at input VAT and reports it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import Money


@dataclass(frozen=True)
class VatRefundInput:
    refund_base: Money  # CNY minor
    input_vat: Money  # CNY minor
    refund_rate_bp: int  # basis points, 0..10_000


@dataclass(frozen=True)
class VatRefundResult:
    refund: Money
    uncapped_refund: Money
    capped_by_input_vat: bool


def export_vat_refund(inp: VatRefundInput) -> VatRefundResult:
    for money_field in (inp.refund_base, inp.input_vat):
        if money_field.currency != "CNY":
            raise ValueError(f"expected CNY, got {money_field.currency}")
    if not 0 <= inp.refund_rate_bp <= 10_000:
        raise ValueError(f"refund_rate_bp out of range: {inp.refund_rate_bp}")
    if inp.refund_base.minor < 0 or inp.input_vat.minor < 0:
        raise ValueError("amounts must be non-negative")

    uncapped = inp.refund_base.rate(inp.refund_rate_bp, 10_000)
    capped = uncapped.minor > inp.input_vat.minor
    refund = inp.input_vat if capped else uncapped
    return VatRefundResult(refund=refund, uncapped_refund=uncapped, capped_by_input_vat=capped)
