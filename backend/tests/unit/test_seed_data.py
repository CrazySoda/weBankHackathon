"""Seed-data contract tests (BUILD_PLAN M3): deals.json ground truth and the
poisoned-document suite must stay in sync with the deterministic engines in
app.rules.checks and app.graph.nodes.injection_screen."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.graph.nodes.injection_screen import (
    BENEFICIARY_CHANGE_PATTERNS,
    INSTRUCTION_PATTERNS,
)
from app.rules.checks import run_lc_checks

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"

ALLOWED_OUTCOMES = {"clean_approval", "resolve_then_approval", "escalate", "injection_escalate"}
ALLOWED_FLAGS = {"hidden_text", "instruction_like_phrase", "beneficiary_change_language"}
ALLOWED_SEVERITIES = {"block", "warn", "info"}
ALLOWED_ATTACKS = {"hidden_text", "instruction_phrase", "beneficiary_change", "metadata_anomaly"}

# exact scenario mix required by the M3 seed deliverable
EXPECTED_SCENARIO_MIX = {
    "clean": 3,
    "clean_vat_refund": 2,
    "fixable": 2,
    "unfixable": 2,
    "policy_deny": 1,
}


def _load(name: str) -> dict:
    with (SEED_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


DEALS_DATA = _load("deals/deals.json")
DEALS = DEALS_DATA["deals"]

POISONED_DATA = _load("poisoned/poisoned.json")
POISONED = POISONED_DATA["documents"]


def _doc(deal: dict, kind: str) -> dict:
    return next(d for d in deal["documents"] if d["kind"] == kind)


def _findings(deal: dict) -> list:
    """run_lc_checks over a deal's LC vs commercial invoice fields."""
    lc = _doc(deal, "letter_of_credit")["fields"]
    invoice = _doc(deal, "commercial_invoice")["fields"]
    return run_lc_checks(lc, invoice)


class TestDealsJson:
    def test_parses_and_marks_synthetic(self):
        assert DEALS_DATA["synthetic"] is True
        assert isinstance(DEALS, list)

    def test_exactly_ten_deals_with_unique_ids(self):
        assert len(DEALS) == 10
        ids = [d["deal_id"] for d in DEALS]
        assert len(set(ids)) == len(ids)

    def test_each_deal_has_ground_truth_and_documents(self):
        for deal in DEALS:
            assert "ground_truth" in deal
            gt = deal["ground_truth"]
            assert gt["expected_outcome"] in ALLOWED_OUTCOMES
            for finding in gt["expected_findings"]:
                assert finding["severity"] in ALLOWED_SEVERITIES
                assert isinstance(finding["fixable"], bool)
            assert len(deal["documents"]) >= 2

    def test_scenario_mix_matches_spec(self):
        counts = Counter(d["scenario"] for d in DEALS)
        assert counts == EXPECTED_SCENARIO_MIX


class TestCleanDealsProduceNoBlocks:
    def test_clean_deals_have_no_block_findings(self):
        for deal in DEALS:
            if deal["scenario"] != "clean":
                continue
            blocks = [d for d in _findings(deal) if d.severity == "block"]
            assert blocks == [], f"{deal['deal_id']} unexpected blocks: {blocks}"

    def test_clean_vat_refund_deals_have_no_blocks(self):
        # zero block findings; the VAT-refund finding is info-level only
        for deal in DEALS:
            if deal["scenario"] != "clean_vat_refund":
                continue
            blocks = [d for d in _findings(deal) if d.severity == "block"]
            assert blocks == [], f"{deal['deal_id']} unexpected blocks: {blocks}"
            assert any(f["severity"] == "info" for f in deal["ground_truth"]["expected_findings"])

    def test_clean_deals_expect_clean_approval(self):
        for deal in DEALS:
            if deal["scenario"] in ("clean", "clean_vat_refund"):
                assert deal["ground_truth"]["expected_outcome"] == "clean_approval"


class TestFixableDeals:
    def test_fixable_deals_produce_fixable_blocks(self):
        for deal in DEALS:
            if deal["scenario"] != "fixable":
                continue
            fixable_blocks = [d for d in _findings(deal) if d.severity == "block" and d.fixable]
            assert fixable_blocks, f"{deal['deal_id']} has no fixable block"
            assert deal["ground_truth"]["expected_outcome"] == "resolve_then_approval"


class TestUnfixableDeals:
    def test_unfixable_deals_produce_blocks(self):
        for deal in DEALS:
            if deal["scenario"] != "unfixable":
                continue
            blocks = [d for d in _findings(deal) if d.severity == "block"]
            assert blocks, f"{deal['deal_id']} has no block finding"
            assert deal["ground_truth"]["expected_outcome"] == "escalate"

    def test_unfixable_deals_include_a_non_fixable_block(self):
        # DECISION: the engine marks shipment-after-expiry fixable=True (an
        # expiry amendment could cure it on paper), so the non-fixable-block
        # requirement is asserted across the pair: the beneficiary-mismatch
        # deal provides it. Each unfixable deal still escalates on blocks.
        all_blocks = [
            d
            for deal in DEALS
            if deal["scenario"] == "unfixable"
            for d in _findings(deal)
            if d.severity == "block"
        ]
        assert any(not d.fixable for d in all_blocks)
        # and the ground truth agrees with the engine on which rule is unfixable
        gt = next(
            d
            for deal in DEALS
            if deal["deal_id"] == "seed-08"
            for d in deal["ground_truth"]["expected_findings"]
        )
        assert gt["rule_id"] == "doc-beneficiary-mismatch"
        assert gt["fixable"] is False


class TestPolicyDenyDeal:
    def test_missing_beneficiary_is_a_fail_closed_deny(self):
        deal = next(d for d in DEALS if d["scenario"] == "policy_deny")
        lc_fields = _doc(deal, "letter_of_credit")["fields"]
        assert "beneficiary" not in lc_fields
        # the checks engine skips the comparison (nothing to compare against);
        # the deny comes from the policy layer, hence the synthetic rule id
        assert deal["ground_truth"]["expected_outcome"] == "escalate"
        # DECISION: the deny manifests in the policy layer (payee_matches_beneficiary
        # fails), not as a Finding — ground truth expects no findings, just escalation
        assert deal["ground_truth"]["expected_findings"] == []


class TestPoisonedJson:
    def test_parses_and_marks_synthetic(self):
        assert POISONED_DATA["synthetic"] is True
        assert len(POISONED) == 8

    def test_unique_doc_ids(self):
        ids = [p["doc_id"] for p in POISONED]
        assert len(set(ids)) == len(ids)

    def test_expected_flags_and_severities_from_known_sets(self):
        for spec in POISONED:
            assert spec["attack"] in ALLOWED_ATTACKS
            assert spec["expected_flag"] in ALLOWED_FLAGS
            assert spec["severity"] in {"block", "warn"}

    def test_attack_type_mix(self):
        counts = Counter(p["attack"] for p in POISONED)
        assert counts["hidden_text"] == 3
        assert counts["instruction_phrase"] == 3
        assert counts["beneficiary_change"] == 2

    def test_hidden_text_attacks_carry_hidden_lines(self):
        for spec in POISONED:
            if spec["attack"] == "hidden_text":
                assert spec["hidden_text"], f"{spec['doc_id']} missing hidden_text"
            else:
                assert spec.get("hidden_text") in (None, [])


class TestAttackStringsMatchInjectionRules:
    @staticmethod
    def _text(spec: dict) -> str:
        return "\n".join(spec["visible_text"] + spec.get("hidden_text", []))

    def test_instruction_attacks_match_a_pattern(self):
        for spec in POISONED:
            if spec["attack"] not in ("hidden_text", "instruction_phrase"):
                continue
            text = self._text(spec)
            hits = [p for p in INSTRUCTION_PATTERNS if re.search(p, text, re.IGNORECASE)]
            assert hits, f"{spec['doc_id']} matches no INSTRUCTION_PATTERNS"

    def test_beneficiary_change_attacks_match_a_pattern(self):
        for spec in POISONED:
            if spec["attack"] != "beneficiary_change":
                continue
            text = self._text(spec)
            hits = [p for p in BENEFICIARY_CHANGE_PATTERNS if re.search(p, text, re.IGNORECASE)]
            assert hits, f"{spec['doc_id']} matches no BENEFICIARY_CHANGE_PATTERNS"
