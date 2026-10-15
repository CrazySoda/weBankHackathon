"""Deterministic LC checks, including the shipment-date and presentation-period rules."""

from __future__ import annotations

from app.rules.checks import (
    check_latest_shipment,
    check_presentation_period,
    run_lc_checks,
)

LC = {
    "lc_amount": "100000.00",
    "currency": "USD",
    "beneficiary": "Shenzhen Sunny Lighting Co., Ltd.",
    "goods_description": "LED desk lamps model L2",
    "quantity": "5000 pcs",
    "expiry_date": "2026-12-31",
    "latest_shipment_date": "2026-11-30",
}
INV = {
    "total_amount": "100000.00",
    "currency": "USD",
    "beneficiary": "Shenzhen Sunny Lighting Co., Ltd.",
    "goods_description": "LED desk lamps model L2",
    "quantity": "5000 pcs",
    "shipment_date": "2026-11-01",
    "presentation_date": "2026-11-09",
}


class TestLatestShipment:
    def test_on_time_ok(self):
        assert check_latest_shipment("2026-11-01", "2026-11-30") is None

    def test_on_the_last_day_ok(self):
        assert check_latest_shipment("2026-11-30", "2026-11-30") is None

    def test_late_is_unfixable_block(self):
        d = check_latest_shipment("2026-12-05", "2026-11-30")
        assert d is not None
        assert (d.rule_id, d.severity, d.fixable) == ("lc-late-shipment", "block", False)

    def test_missing_dates_skip(self):
        assert check_latest_shipment(None, "2026-11-30") is None
        assert check_latest_shipment("2026-11-01", None) is None

    def test_unparseable_warns(self):
        d = check_latest_shipment("soon", "2026-11-30")
        assert d is not None and d.rule_id == "doc-date-unparseable"
        d = check_latest_shipment("2026-11-01", "later")
        assert d is not None and d.rule_id == "doc-date-unparseable"


class TestPresentationPeriod:
    def test_within_21_days_ok(self):
        assert check_presentation_period("2026-11-01", "2026-11-22", "2026-12-31") is None

    def test_day_22_is_late(self):
        d = check_presentation_period("2026-11-01", "2026-11-23", "2026-12-31")
        assert d is not None
        assert (d.rule_id, d.fixable) == ("ucp-late-presentation", False)

    def test_after_expiry_is_blocked_first(self):
        d = check_presentation_period("2026-12-20", "2027-01-05", "2026-12-31")
        assert d is not None and d.rule_id == "ucp-presentation-after-expiry"

    def test_no_expiry_still_checks_21_days(self):
        d = check_presentation_period("2026-11-01", "2026-12-01", None)
        assert d is not None and d.rule_id == "ucp-late-presentation"

    def test_missing_dates_skip(self):
        assert check_presentation_period(None, "2026-11-09", None) is None
        assert check_presentation_period("2026-11-01", None, None) is None

    def test_unparseable_warns(self):
        d = check_presentation_period("2026-11-01", "tomorrow", None)
        assert d is not None and d.rule_id == "doc-date-unparseable"
        d = check_presentation_period("yesterday", "2026-11-09", None)
        assert d is not None and d.rule_id == "doc-date-unparseable"


class TestBattery:
    def test_hero_deal_is_clean(self):
        assert run_lc_checks(LC, INV) == []

    def test_late_shipment_found_by_battery(self):
        late = {**INV, "shipment_date": "2026-12-05", "presentation_date": "2026-12-10"}
        assert [d.rule_id for d in run_lc_checks(LC, late)] == ["lc-late-shipment"]

    def test_over_invoicing_found(self):
        over = {**INV, "total_amount": "120000.00"}
        assert [d.rule_id for d in run_lc_checks(LC, over)] == ["lc-invoice-exceeds-lc"]

    def test_late_presentation_found_by_battery(self):
        slow = {**INV, "presentation_date": "2026-11-28"}
        assert [d.rule_id for d in run_lc_checks(LC, slow)] == ["ucp-late-presentation"]
