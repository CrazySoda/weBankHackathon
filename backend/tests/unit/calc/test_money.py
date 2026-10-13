"""Money primitive: integers only, currency safety, canonical hashing."""

from decimal import Decimal

import pydantic
import pytest
from app.calc.money import CurrencyMismatch, Money, UnknownCurrency, canonical_json, sha256_hex
from hypothesis import given
from hypothesis import strategies as st


class TestConstruction:
    def test_from_major_string(self):
        assert Money.from_major("1234.56", "USD") == Money(minor=123456, currency="USD")

    def test_from_major_half_up(self):
        assert Money.from_major("0.125", "USD") == Money(minor=13, currency="USD")
        assert Money.from_major("0.124", "USD") == Money(minor=12, currency="USD")

    def test_zero_exponent_currency(self):
        # JPY has no minor units
        assert Money.from_major(1000, "JPY") == Money(minor=1000, currency="JPY")

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            Money.from_major(1.5, "USD")  # type: ignore[arg-type]

    def test_unknown_currency(self):
        # pydantic wraps the validator's UnknownCurrency into a ValidationError
        with pytest.raises((UnknownCurrency, pydantic.ValidationError), match="XYZ"):
            Money(minor=1, currency="XYZ")

    def test_lowercase_currency_rejected(self):
        with pytest.raises(ValueError, match="upper-case"):
            Money(minor=1, currency="usd")


class TestArithmetic:
    def test_add_sub(self):
        a = Money(minor=100, currency="CNY")
        b = Money(minor=250, currency="CNY")
        assert a + b == Money(minor=350, currency="CNY")
        assert b - a == Money(minor=150, currency="CNY")

    def test_currency_mismatch(self):
        with pytest.raises(CurrencyMismatch):
            Money(minor=1, currency="CNY") + Money(minor=1, currency="USD")

    def test_neg(self):
        assert -Money(minor=5, currency="BDT") == Money(minor=-5, currency="BDT")

    def test_scaled_half_up(self):
        m = Money(minor=100, currency="USD")
        assert m.rate(15, 100) == Money(minor=15, currency="USD")
        assert m.scaled(1, 3) == Money(minor=33, currency="USD")  # 33.33 -> 33
        assert Money(minor=5, currency="USD").scaled(1, 2) == Money(minor=3, currency="USD")
        assert Money(minor=-5, currency="USD").scaled(1, 2) == Money(minor=-3, currency="USD")
        with pytest.raises(ZeroDivisionError):
            m.scaled(1, 0)

    def test_comparisons(self):
        a = Money(minor=1, currency="USD")
        b = Money(minor=2, currency="USD")
        assert a < b and a <= b and b > a and b >= a
        with pytest.raises(CurrencyMismatch):
            result = a < Money(minor=0, currency="EUR")
            assert result is not None  # pragma: no mutate - exception is the point

    def test_comparisons_with_non_money_return_not_implemented(self):
        a = Money(minor=1, currency="USD")
        assert a.__lt__(5) is NotImplemented
        assert a.__le__(None) is NotImplemented
        assert a.__gt__("x") is NotImplemented
        assert a.__ge__(object()) is NotImplemented
        # B015-free form: comparisons used for their exception side effect

    def test_add_bool_minor_rejected(self):
        # strict mode: bool is not coerced to int
        with pytest.raises(pydantic.ValidationError):
            Money(minor=True, currency="USD")  # type: ignore[arg-type]

    def test_to_major_decimal(self):
        assert Money(minor=123456, currency="USD").to_major_decimal() == Decimal("1234.56")
        assert Money(minor=1000, currency="JPY").to_major_decimal() == Decimal(1000)

    def test_canonical_form(self):
        assert Money(minor=5, currency="USD").canonical() == {"minor": 5, "currency": "USD"}

    def test_sha256_of_bytes(self):
        assert sha256_hex(b"abc") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_frozen(self):
        m = Money(minor=1, currency="USD")
        with pytest.raises(pydantic.ValidationError, match="frozen"):
            m.minor = 2  # type: ignore[misc]


class TestCanonical:
    def test_canonical_json_sorted(self):
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_sha256_hex(self):
        assert sha256_hex("") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )


@given(
    minor=st.integers(min_value=-(10**12), max_value=10**12),
    num=st.integers(min_value=0, max_value=10_000),
    den=st.integers(min_value=1, max_value=10_000),
)
def test_scaled_never_excedes_exact_ratio(minor: int, num: int, den: int):
    """scaled() result differs from exact ratio by < 1 minor unit."""
    m = Money(minor=minor, currency="CNY")
    exact = Decimal(minor) * Decimal(num) / Decimal(den)
    got = m.scaled(num, den)
    assert abs(Decimal(got.minor) - exact) < 1


@given(st.integers(min_value=0, max_value=10_000), st.integers(min_value=1, max_value=999))
def test_rate_inverse(rate_bp: int, minor: int):
    """rate(rate_bp, 10000) never exceeds the base (a percentage can't add money)."""
    m = Money(minor=minor, currency="USD")
    r = m.rate(rate_bp, 10_000)
    if minor >= 0 and rate_bp <= 10_000:
        assert abs(r.minor) <= abs(minor)
