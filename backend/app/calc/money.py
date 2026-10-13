"""Money primitive: integer minor units + ISO 4217 code. Never floats (rule 0.9).

All calculators in `app.calc` accept/return `Money` or bare integer minor units
paired with an explicit currency. Arithmetic across mismatched currencies raises
`CurrencyMismatch` instead of converting implicitly.
"""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ISO 4217 minor-unit exponents for currencies used in the demo flow.
MINOR_UNITS: dict[str, int] = {
    "CNY": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "BDT": 2,
    "HKD": 2,
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "XAU": 0,
}


class CurrencyMismatch(ArithmeticError):
    """Raised when money in different currencies is combined without conversion."""


class UnknownCurrency(ValueError):
    pass


def minor_exponent(currency: str) -> int:
    try:
        return MINOR_UNITS[currency]
    except KeyError:
        raise UnknownCurrency(currency) from None


class Money(BaseModel):
    """Immutable amount in integer minor units with an ISO 4217 currency."""

    model_config = ConfigDict(frozen=True, strict=True)  # strict: no str/bool→int coercion

    minor: int = Field(strict=True)
    currency: str = Field(strict=True, min_length=3, max_length=3)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.currency != self.currency.upper() or not self.currency.isalpha():
            raise ValueError(f"currency must be upper-case ISO 4217 code, got {self.currency!r}")
        minor_exponent(self.currency)  # raises UnknownCurrency for unsupported codes
        return self

    # -- construction helpers -------------------------------------------------

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(minor=0, currency=currency)

    @classmethod
    def from_major(cls, amount: str | int | Decimal, currency: str) -> Money:
        """Convert a major-unit decimal (e.g. "1234.56") to minor units.

        Accepts str/Decimal/int only — floats are rejected by design.
        """
        if isinstance(amount, float):  # pragma: no cover - explicit guard
            raise TypeError("Money.from_major refuses floats; pass str, int or Decimal")
        exp = minor_exponent(currency)
        d = (Decimal(amount) * (10**exp)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(minor=int(d), currency=currency)

    def to_major_decimal(self) -> Decimal:
        result: Decimal = Decimal(self.minor) / (10 ** minor_exponent(self.currency))
        return result

    # -- arithmetic -----------------------------------------------------------

    def _assert_same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._assert_same(other)
        return Money(minor=self.minor + other.minor, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same(other)
        return Money(minor=self.minor - other.minor, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(minor=-self.minor, currency=self.currency)

    def scaled(self, numerator: int, denominator: int) -> Money:
        """Exact integer scaling: minor * numerator / denominator, half-up rounding."""
        if denominator == 0:
            raise ZeroDivisionError("denominator must be non-zero")
        num = self.minor * numerator
        # half-up on the sign-adjusted absolute value
        sign = -1 if num < 0 else 1
        q, r = divmod(abs(num), denominator)
        if 2 * r >= denominator:
            q += 1
        return Money(minor=sign * q, currency=self.currency)

    def rate(self, numerator: int, denominator: int) -> Money:
        """Alias of :meth:`scaled` for percentage-style reads (rate(15,100) = 15%)."""
        return self.scaled(numerator, denominator)

    # -- comparison -----------------------------------------------------------

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same(other)
        return self.minor < other.minor

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same(other)
        return self.minor <= other.minor

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same(other)
        return self.minor > other.minor

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same(other)
        return self.minor >= other.minor

    # -- serialization --------------------------------------------------------

    def canonical(self) -> dict[str, object]:
        """Canonical, hash-stable form used in deal hashes and audit events."""
        return {"minor": self.minor, "currency": self.currency}


def canonical_json(obj: object) -> str:
    """JSON with sorted keys and no whitespace — the canonical form for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
