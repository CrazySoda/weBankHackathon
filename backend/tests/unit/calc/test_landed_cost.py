"""Landed cost reference cases + validation."""

import pytest
from app.calc.landed_cost import LandedCostInput, landed_cost_bdt
from app.calc.money import CurrencyMismatch, Money


def bdt(minor: int) -> Money:
    return Money(minor=minor, currency="BDT")


class TestReferenceCases:
    def test_full_case(self):
        # goods 500,000.00 + freight 20,000.00 + insurance 2,000.00 = CIF 522,000.00
        # duty 10% = 52,200.00 ; AIT 5% = 26,100.00 ; flat fees 5,000.00
        r = landed_cost_bdt(
            LandedCostInput(
                goods_value=bdt(50_000_000),
                freight=bdt(2_000_000),
                insurance=bdt(200_000),
                duty_rate_bp=1000,
                flat_fees=(bdt(500_000),),
            )
        )
        assert r.cif == bdt(52_200_000)
        assert r.duty == bdt(5_220_000)
        assert r.ait == bdt(2_610_000)
        assert r.fees_total == bdt(500_000)
        assert r.landed_total == bdt(60_530_000)

    def test_no_fees_no_insurance(self):
        r = landed_cost_bdt(
            LandedCostInput(
                goods_value=bdt(1_000_000),
                freight=bdt(0),
                insurance=bdt(0),
                duty_rate_bp=0,
                ait_rate_bp=0,
            )
        )
        assert r.landed_total == bdt(1_000_000)

    def test_rounding_half_up(self):
        # CIF 33.33 -> duty 10% = 3.333 -> 3.33 minor half-up on 3.333 => 3
        r = landed_cost_bdt(
            LandedCostInput(
                goods_value=bdt(3333), freight=bdt(0), insurance=bdt(0), duty_rate_bp=1000
            )
        )
        assert r.duty == bdt(333)  # 333.3 -> 333


class TestValidation:
    def test_rejects_non_bdt(self):
        with pytest.raises(CurrencyMismatch):
            landed_cost_bdt(
                LandedCostInput(
                    goods_value=Money(minor=1, currency="USD"),
                    freight=bdt(0),
                    insurance=bdt(0),
                    duty_rate_bp=0,
                )
            )

    @pytest.mark.parametrize("rate", [-5, 12_345])
    def test_rate_bounds(self, rate: int):
        with pytest.raises(ValueError, match="out of range"):
            landed_cost_bdt(
                LandedCostInput(
                    goods_value=bdt(1), freight=bdt(0), insurance=bdt(0), duty_rate_bp=rate
                )
            )

    def test_negative_amount(self):
        with pytest.raises(ValueError, match="non-negative"):
            landed_cost_bdt(
                LandedCostInput(
                    goods_value=bdt(-1), freight=bdt(0), insurance=bdt(0), duty_rate_bp=0
                )
            )
