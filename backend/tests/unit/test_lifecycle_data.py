"""Lifecycle corpus contract: ground truth must agree with the real engines.

Nothing here trusts the generator's own numbers: every outcome is recomputed
through ``app.rules.checks``, ``app.calc`` and the injection screen.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.calc.fx import RATE_SCALE, FxQuote, effective_fx_cost
from app.calc.landed_cost import ImportTaxInput, import_tax_stack_bdt
from app.calc.money import Money
from app.calc.vat_refund import VatRefundInput, export_vat_refund
from app.graph.nodes.injection_screen import screen_spans
from app.harness.document_parsing import full_text, parse_pdf_spans
from app.rules.checks import run_lc_checks
from app.rules.loader import load_rule_pack
from app.rules.store import rules_in_force

LIFECYCLE = Path(__file__).resolve().parents[2] / "seed" / "lifecycle"
DATA = json.loads((LIFECYCLE / "lifecycle.json").read_text(encoding="utf-8"))
DEALS = {d["deal_id"]: d for d in DATA["deals"]}
ROLES = set(DATA["roles"])


def d(s: str) -> date:
    return date.fromisoformat(s)


def banking_days_between(start: date, end: date) -> int:
    """Weekdays after ``start`` up to and including ``end`` (no holiday calendar)."""
    n, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def minor(value: str) -> int:
    return int((Decimal(value.replace(",", "")) * 100).quantize(Decimal(1)))


def doc_of(deal: dict, doc_id: str) -> dict:
    return next(x for x in deal["documents"] if x["doc_id"] == doc_id)


class TestShape:
    def test_four_deals_all_synthetic(self):
        assert list(DEALS) == ["HD-01", "HD-02", "HD-03", "HD-04"]
        assert DATA["synthetic"] is True
        assert all(x["synthetic"] for x in DATA["deals"])

    def test_all_four_roles_present_in_parties(self):
        for deal in DATA["deals"]:
            assert {"seller", "buyer", "issuing_bank", "advising_bank"} == ROLES
            assert set(deal["parties"]) >= ROLES

    def test_both_parties_upload_and_bank_issues(self):
        hero = DEALS["HD-01"]
        origins = {x["origin"] for x in hero["documents"]}
        assert origins == {"seller_upload", "buyer_upload", "bank_issued"}

    def test_visibility_roles_valid_and_buyer_gets_release(self):
        for deal in DATA["deals"]:
            for x in deal["documents"]:
                assert set(x["visible_to"]) <= ROLES, x["doc_id"]
        release = doc_of(DEALS["HD-01"], "D17")
        assert release["visible_to"] == ["buyer", "issuing_bank"]
        assert release["origin"] == "bank_issued"

    def test_doc_ids_unique_within_deal(self):
        for deal in DATA["deals"]:
            ids = [x["doc_id"] for x in deal["documents"]]
            assert len(ids) == len(set(ids)), deal["deal_id"]


class TestTimeline:
    @pytest.mark.parametrize("deal_id", list(DEALS))
    def test_sequence_dates_and_references(self, deal_id):
        deal = DEALS[deal_id]
        events = deal["timeline"]
        assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
        dates = [d(e["date"]) for e in events]
        assert dates == sorted(dates)
        known = {x["doc_id"] for x in deal["documents"]}
        referenced = {i for e in events for i in e["doc_ids"]}
        assert referenced <= known
        assert known <= referenced, f"unreferenced documents: {known - referenced}"

    @pytest.mark.parametrize("deal_id", list(DEALS))
    def test_document_dates_match_their_event_or_come_earlier(self, deal_id):
        deal = DEALS[deal_id]
        for e in deal["timeline"]:
            for doc_id in e["doc_ids"]:
                assert d(doc_of(deal, doc_id)["doc_date"]) <= d(e["date"]), doc_id


class TestUcpTiming:
    def test_hero_presentation_and_examination_windows(self):
        hero = DEALS["HD-01"]
        bl = d(doc_of(hero, "D09")["doc_date"])
        presented = d(doc_of(hero, "D14")["fields"]["presentation_date"])
        examined = d(doc_of(hero, "D15")["fields"]["examination_date"])
        assert (presented - bl).days <= 21
        assert presented <= d(doc_of(hero, "D04")["fields"]["expiry_date"])
        assert banking_days_between(presented, examined) <= 5

    def test_resolved_deal_reexamination_window(self):
        deal = DEALS["HD-02"]
        bl = d(doc_of(deal, "D09")["doc_date"])
        again = d(doc_of(deal, "D14R")["fields"]["presentation_date"])
        done = d(doc_of(deal, "D15R")["fields"]["examination_date"])
        assert (again - bl).days <= 21
        assert banking_days_between(again, done) <= 5

    def test_every_examination_is_within_five_banking_days(self):
        for deal in DATA["deals"]:
            for x in deal["documents"]:
                if x["kind"] != "examination_result":
                    continue
                f = x["fields"]
                gap = banking_days_between(d(f["presentation_date"]), d(f["examination_date"]))
                assert gap <= 5, (deal["deal_id"], x["doc_id"], gap)

    def test_draft_maturity_is_sixty_days_after_bl(self):
        drafts = [
            x
            for deal in DATA["deals"]
            for x in deal["documents"]
            if x["kind"] == "bill_of_exchange"
        ]
        assert len(drafts) == 4  # HD-01, HD-02 (original + revised), HD-03; none for HD-04
        for draft in drafts:
            bl = d(draft["fields"]["bl_date"])
            assert d(draft["fields"]["maturity_date"]) == bl + timedelta(days=60)


class TestChecksEngineAgreesWithGroundTruth:
    @pytest.mark.parametrize("deal_id", list(DEALS))
    def test_initial_findings(self, deal_id):
        deal = DEALS[deal_id]
        ci = deal["check_inputs_initial"]
        found = [x.rule_id for x in run_lc_checks(ci["lc"], ci["invoice"])]
        assert found == deal["expected"]["initial_rule_ids"]

    @pytest.mark.parametrize("deal_id", list(DEALS))
    def test_final_findings(self, deal_id):
        deal = DEALS[deal_id]
        ci = deal["check_inputs_final"]
        found = [x.rule_id for x in run_lc_checks(ci["lc"], ci["invoice"])]
        assert found == deal["expected"]["final_rule_ids"]

    def test_unfixable_late_shipment_is_not_fixable(self):
        ci = DEALS["HD-03"]["check_inputs_initial"]
        (finding,) = run_lc_checks(ci["lc"], ci["invoice"])
        assert finding.fixable is False and finding.severity == "block"

    def test_over_invoice_is_fixable(self):
        ci = DEALS["HD-02"]["check_inputs_initial"]
        (finding,) = run_lc_checks(ci["lc"], ci["invoice"])
        assert finding.fixable is True


class TestDocumentArithmetic:
    @pytest.mark.parametrize("deal_id", ["HD-01", "HD-03", "HD-04"])
    def test_invoice_total_is_qty_times_unit_price(self, deal_id):
        inv = doc_of(DEALS[deal_id], "D06")["fields"]
        qty = int(inv["quantity"].split()[0])
        unit = minor(inv["unit_price"].split()[1])
        assert minor(inv["total_amount"]) == qty * unit

    def test_hero_insurance_is_110_percent_of_cif(self):
        hero = DEALS["HD-01"]
        cif = minor(doc_of(hero, "D06")["fields"]["total_amount"])
        insured = minor(doc_of(hero, "D11")["fields"]["sum_insured"])
        assert insured == cif * 110 // 100

    def test_packing_list_matches_invoice_quantity(self):
        hero = DEALS["HD-01"]
        packing_qty = doc_of(hero, "D07")["fields"]["quantity"]
        assert packing_qty == doc_of(hero, "D06")["fields"]["quantity"]
        cartons = int(doc_of(hero, "D07")["fields"]["cartons"].split()[0])
        assert cartons * 20 == int(doc_of(hero, "D06")["fields"]["quantity"].split()[0])

    def test_bl_and_invoice_agree_on_shipment_date(self):
        for deal in DATA["deals"]:
            bl = doc_of(deal, "D09")["fields"]
            inv = doc_of(deal, "D06")["fields"]
            assert bl["shipment_date"] == inv["shipment_date"] == bl["shipped_on_board_date"]

    def test_customs_value_is_fob_below_cif(self):
        hero = DEALS["HD-01"]
        cust = doc_of(hero, "D08")["fields"]
        fob = minor(cust["customs_value_usd"])
        assert fob < minor(doc_of(hero, "D06")["fields"]["total_amount"])
        rate = Decimal(cust["customs_exchange_rate_cny"])
        assert minor(cust["customs_value_cny"]) == int((Decimal(fob) * rate).quantize(Decimal(1)))


class TestCalculatorsAgreeWithDocuments:
    """The numbers printed on bank and customs documents come from calc/."""

    def test_export_vat_refund_is_capped_by_input_vat(self):
        spec = DATA["reference"]["hero_calculations"]["export_vat_refund"]
        hero = DEALS["HD-01"]
        base = minor(doc_of(hero, "D08")["fields"]["customs_value_cny"])
        input_vat = minor(doc_of(hero, "D13")["fields"]["input_vat_cny"])
        assert base == spec["refund_base_cny_minor"]
        assert input_vat == spec["input_vat_cny_minor"]
        r = export_vat_refund(
            VatRefundInput(
                refund_base=Money(minor=base, currency="CNY"),
                input_vat=Money(minor=input_vat, currency="CNY"),
                refund_rate_bp=spec["refund_rate_bp"],
            )
        )
        assert r.capped_by_input_vat is True
        assert r.refund.minor == input_vat

    def test_fx_statement_matches_effective_fx_cost(self):
        spec = DATA["reference"]["hero_calculations"]["fx"]
        stmt = doc_of(DEALS["HD-01"], "D20")["fields"]
        r = effective_fx_cost(
            Money(minor=spec["sell_usd_minor"], currency="USD"),
            FxQuote(
                route_id="cny-direct",
                sell_currency="USD",
                buy_currency="CNY",
                mid_rate_scaled=spec["mid_rate_scaled"],
                spread_bp=spec["spread_bp"],
                fee=Money(minor=spec["fee_cny_minor"], currency="CNY"),
                provider="synthetic:cny-direct",
            ),
        )
        assert r.converted_gross.minor == minor(stmt["gross_cny"])
        assert r.spread_amount.minor == minor(stmt["spread_cny"])
        assert r.net.minor == minor(stmt["net_cny"]) == spec["net_cny_minor"]
        assert Decimal(stmt["effective_rate"]) == Decimal(r.effective_rate_scaled) / RATE_SCALE

    def test_bill_of_entry_matches_import_tax_stack(self):
        boe = doc_of(DEALS["HD-01"], "D18")["fields"]
        rate = Decimal(boe["customs_exchange_rate_bdt"])
        av = int((Decimal(minor(boe["cif_value_usd"])) * rate).quantize(Decimal(1)))
        assert av == minor(boe["assessable_value_bdt"])
        spec = DATA["reference"]["hero_calculations"]["import_tax"]
        r = import_tax_stack_bdt(
            ImportTaxInput(
                assessable_value=Money(minor=av, currency="BDT"),
                cd_bp=spec["cd_bp"],
                rd_bp=spec["rd_bp"],
                sd_bp=spec["sd_bp"],
                vat_bp=spec["vat_bp"],
                ait_bp=spec["ait_bp"],
            )
        )
        assert r.customs_duty.minor == minor(boe["customs_duty_bdt"])
        assert r.regulatory_duty.minor == minor(boe["regulatory_duty_bdt"])
        assert r.supplementary_duty.minor == minor(boe["supplementary_duty_bdt"])
        assert r.vat.minor == minor(boe["vat_bdt"])
        assert r.ait.minor == minor(boe["ait_bdt"])
        assert r.total_taxes.minor == minor(boe["total_taxes_bdt"]) == spec["total_taxes_bdt_minor"]

    def test_rates_used_equal_the_flagged_demo_rules(self):
        rows = load_rule_pack()
        spec = DATA["reference"]["hero_calculations"]
        on = d("2026-11-24")
        bd = {r.rule_id: r for r in rules_in_force(rows, "BD", "import_duty", on)}
        cn = {r.rule_id: r for r in rules_in_force(rows, "CN", "vat_refund", d("2026-10-31"))}
        duty = bd["bd-duty-9405-lamps"].content
        assert (duty["cd_bp"], duty["rd_bp"], duty["sd_bp"]) == (
            spec["import_tax"]["cd_bp"],
            spec["import_tax"]["rd_bp"],
            spec["import_tax"]["sd_bp"],
        )
        assert bd["bd-vat-standard"].content["vat_bp"] == spec["import_tax"]["vat_bp"]
        assert bd["bd-ait-import"].content["ait_bp"] == spec["import_tax"]["ait_bp"]
        assert cn["cn-vat-rate-9405-lamps"].content["refund_rate_bp"] == (
            spec["export_vat_refund"]["refund_rate_bp"]
        )


class TestPdfsOnDisk:
    def all_specs(self):
        return [(deal["deal_id"], x) for deal in DATA["deals"] for x in deal["documents"]]

    def test_every_document_has_a_pdf_with_banner_and_fields(self):
        for deal_id, spec in self.all_specs():
            path = LIFECYCLE / "pdfs" / deal_id / spec["filename"]
            assert path.is_file(), path
            text = full_text(parse_pdf_spans(path.read_bytes()))
            assert "SYNTHETIC DEMO DOCUMENT" in text, path
            for key in ("lc_number", "invoice_number", "bl_number"):
                if key in spec["fields"]:
                    assert f"{key}: {spec['fields'][key]}" in text, (path, key)

    def test_lc_spans_multiple_pages_without_losing_lines(self):
        lc = doc_of(DEALS["HD-01"], "D04")
        text = full_text(parse_pdf_spans((LIFECYCLE / "pdfs/HD-01" / lc["filename"]).read_bytes()))
        assert f"confirmation: {lc['fields']['confirmation']}" in text  # last field

    def test_only_the_poisoned_invoice_trips_the_injection_screen(self):
        for deal_id, spec in self.all_specs():
            path = LIFECYCLE / "pdfs" / deal_id / spec["filename"]
            flags = screen_spans(parse_pdf_spans(path.read_bytes()), spec["doc_id"])
            if deal_id == "HD-04" and spec["doc_id"] == "D06":
                kinds = {f.kind for f in flags}
                assert set(DEALS["HD-04"]["expected"]["injection_flags"]) <= kinds
                assert any(f.severity == "block" for f in flags)
            else:
                assert flags == [], (deal_id, spec["doc_id"], flags)

    def test_pdf_generation_is_deterministic(self, tmp_path):
        import importlib.util

        gen = importlib.util.spec_from_file_location("lc_generate", LIFECYCLE / "generate.py")
        assert gen and gen.loader
        mod = importlib.util.module_from_spec(gen)
        gen.loader.exec_module(mod)
        pymupdf = mod.load_pymupdf()
        spec = doc_of(DEALS["HD-01"], "D04")
        out = tmp_path / "again.pdf"
        mod.render_pdf(pymupdf, spec, out)
        existing = (LIFECYCLE / "pdfs/HD-01" / spec["filename"]).read_bytes()
        assert out.read_bytes() == existing

    def test_generated_json_is_in_sync_with_the_generator(self):
        import importlib.util

        gen = importlib.util.spec_from_file_location("lc_generate", LIFECYCLE / "generate.py")
        assert gen and gen.loader
        mod = importlib.util.module_from_spec(gen)
        gen.loader.exec_module(mod)
        assert json.loads(json.dumps(mod.build(), ensure_ascii=False)) == DATA
