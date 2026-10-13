"""Export VAT refund: reference cases + property tests."""

import pytest
from app.calc.money import Money
from app.calc.vat_refund import VatRefundInput, export_vat_refund
from hypothesis import given
from hypothesis import strategies as st


def _cny(minor: int) -> Money:
    return Money(minor=minor, currency="CNY")


class TestReferenceCases:
    def test_basic_13pct(self):
        # 1,000,000.00 CNY base at 13% -> 130,000.00 CNY refund, not capped
        r = export_vat_refund(VatRefundInput(_cny(100_000_000), _cny(200_000_00), 1300))
        assert r.refund == _cny(13_000_000)
        assert not r.capped_by_input_vat

    def test_capped_by_input_vat(self):
        # base * 13% = 130,000 CNY but only 50,000 CNY VAT paid
        r = export_vat_refund(VatRefundInput(_cny(100_000_000), _cny(5_000_000), 1300))
        assert r.refund == _cny(5_000_000)
        assert r.capped_by_input_vat

    def test_half_up_rounding(self):
        # 0.13 * 123.45 base... base=12_345 minor, 1300bp -> 1604.85 -> 1605
        r = export_vat_refund(VatRefundInput(_cny(12_345), _cny(99_999), 1300))
        assert r.refund == _cny(1605)

    def test_zero_rate(self):
        r = export_vat_refund(VatRefundInput(_cny(1_000), _cny(1_000), 0))
        assert r.refund == _cny(0)


class TestValidation:
    def test_currency_mismatch(self):
        with pytest.raises(ValueError, match="expected CNY"):
            export_vat_refund(VatRefundInput(Money(minor=1, currency="USD"), _cny(1), 1300))

    @pytest.mark.parametrize("rate", [-1, 10_001])
    def test_rate_bounds(self, rate: int):
        with pytest.raises(ValueError, match="out of range"):
            export_vat_refund(VatRefundInput(_cny(1), _cny(1), rate))

    def test_negative_amount(self):
        with pytest.raises(ValueError, match="non-negative"):
            export_vat_refund(VatRefundInput(_cny(-1), _cny(1), 1300))


@given(
    base=st.integers(min_value=0, max_value=10**11),
    vat=st.integers(min_value=0, max_value=10**11),
    rate=st.integers(min_value=0, max_value=10_000),
)
def test_refund_never_exceeds_input_vat(base: int, vat: int, rate: int):
    r = export_vat_refund(VatRefundInput(_cny(base), _cny(vat), rate))
    assert r.refund.minor <= vat
    assert r.refund.minor >= 0


@given(
    base=st.integers(min_value=0, max_value=10**11),
    vat=st.integers(min_value=0, max_value=10**11),
    rate=st.integers(min_value=0, max_value=10_000),
)
def test_refund_monotonic_in_rate(base: int, vat: int, rate: int):
    """Uncapped refund is monotone in the rebate rate."""
    lo = export_vat_refund(VatRefundInput(_cny(base), _cny(vat), rate)).uncapped_refund
    hi_rate = min(rate + 1, 10_000)
    hi = export_vat_refund(VatRefundInput(_cny(base), _cny(vat), hi_rate)).uncapped_refund
    assert lo.minor <= hi.minor
