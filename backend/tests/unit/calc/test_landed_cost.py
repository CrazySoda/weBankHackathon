"""Landed cost reference cases + validation."""

import pytest
from app.calc.landed_cost import (
    ImportTaxInput,
    LandedCostInput,
    import_tax_stack_bdt,
    landed_cost_bdt,
)
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


class TestImportTaxStack:
    def test_hero_deal_reference_case(self):
        # AV BDT 12,200,000.00 (USD 100,000 at the demo customs rate 122.00)
        # CD 25% = 3,050,000.00 ; RD 3% = 366,000.00 ; SD 0
        # VAT 15% of (12,200,000 + 3,050,000 + 366,000) = 15,616,000 -> 2,342,400.00
        # AIT 5% of AV = 610,000.00 ; total = 6,368,400.00
        r = import_tax_stack_bdt(
            ImportTaxInput(assessable_value=bdt(1_220_000_000), cd_bp=2500, rd_bp=300)
        )
        assert r.customs_duty == bdt(305_000_000)
        assert r.regulatory_duty == bdt(36_600_000)
        assert r.supplementary_duty == bdt(0)
        assert r.vat == bdt(234_240_000)
        assert r.ait == bdt(61_000_000)
        assert r.total_taxes == bdt(636_840_000)

    def test_supplementary_duty_feeds_vat(self):
        # AV 1,000.00 ; CD 10% = 100 ; RD 0 ; SD 20% of 1,100 = 220 ; VAT 15% of 1,320 = 198
        r = import_tax_stack_bdt(
            ImportTaxInput(assessable_value=bdt(100_000), cd_bp=1000, sd_bp=2000)
        )
        assert r.supplementary_duty == bdt(22_000)
        assert r.vat == bdt(19_800)

    def test_zero_value_is_zero_tax(self):
        r = import_tax_stack_bdt(ImportTaxInput(assessable_value=bdt(0), cd_bp=2500))
        assert r.total_taxes == bdt(0)

    def test_rejects_non_bdt(self):
        with pytest.raises(CurrencyMismatch):
            import_tax_stack_bdt(
                ImportTaxInput(assessable_value=Money(minor=1, currency="USD"), cd_bp=0)
            )

    def test_rejects_negative_value(self):
        with pytest.raises(ValueError, match="non-negative"):
            import_tax_stack_bdt(ImportTaxInput(assessable_value=bdt(-1), cd_bp=0))

    @pytest.mark.parametrize("field", ["cd_bp", "rd_bp", "sd_bp", "vat_bp", "ait_bp"])
    @pytest.mark.parametrize("rate", [-1, 10_001])
    def test_rate_bounds(self, field: str, rate: int):
        kwargs = {"assessable_value": bdt(100), "cd_bp": 0, field: rate}
        with pytest.raises(ValueError, match="rate out of range"):
            import_tax_stack_bdt(ImportTaxInput(**kwargs))
