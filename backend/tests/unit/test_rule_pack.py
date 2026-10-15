"""The curated rule pack is well-formed, sourced, honest and bitemporally queryable."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from app.rules.loader import (
    RulePackError,
    load_rule_pack,
    unverified_rule_ids,
)
from app.rules.store import rules_in_force


@pytest.fixture(scope="module")
def rows():
    return load_rule_pack()


class TestPackIntegrity:
    def test_covers_all_four_priority_areas(self, rows):
        topics = {(r.jurisdiction, r.topic) for r in rows}
        assert ("CN", "vat_refund") in topics
        assert ("BD", "import_duty") in topics
        assert ("BD", "import_docs") in topics
        assert ("INT", "ucp600") in topics
        assert ("INT", "sanctions") in topics

    def test_every_rule_has_source_and_summary(self, rows):
        for r in rows:
            assert r.source_url.startswith(("http://", "https://")), r.rule_id
            assert r.content["_meta"]["summary"], r.rule_id
            assert r.content["_meta"]["source_title"], r.rule_id

    def test_nothing_is_claimed_verified_without_a_primary_source(self, rows):
        # No primary source was fetched for this pack: it must say so.
        assert all(not r.content["_meta"]["verified"] for r in rows)
        assert unverified_rule_ids(rows)

    def test_demo_assumptions_are_flagged(self, rows):
        demo = [r for r in rows if r.content["_meta"]["demo_assumption"]]
        assert {r.rule_id for r in demo} == {"cn-vat-rate-9405-lamps", "bd-duty-9405-lamps"}
        assert all(r.content["_meta"]["summary"].startswith("DEMO ASSUMPTION") for r in demo)

    def test_unresolved_conflicts_carry_no_computable_value(self, rows):
        window = next(r for r in rows if r.rule_id == "cn-vat-claim-window")
        assert window.content["days_after_declaration"] is None
        assert window.content["status"] == "unresolved"


class TestBitemporal:
    def test_battery_rate_changes_at_boundaries(self, rows):
        def rate(on: date) -> int | None:
            found = rules_in_force(rows, "CN", "vat_refund", on)
            hit = [r for r in found if r.rule_id == "cn-vat-rate-battery"]
            return hit[0].content["refund_rate_bp"] if hit else None

        assert rate(date(2026, 3, 31)) is None  # before the announcement takes effect
        assert rate(date(2026, 4, 1)) == 600
        assert rate(date(2026, 12, 31)) == 600
        assert rate(date(2027, 1, 1)) == 0

    def test_ucp_rules_in_force_for_current_deal(self, rows):
        ids = {r.rule_id for r in rules_in_force(rows, "INT", "ucp600", date(2026, 10, 15))}
        assert "ucp-art14b-examination-period" in ids
        assert "ucp-art18-commercial-invoice" in ids


class TestLoaderFailsClosed:
    def _pack(self, tmp_path: Path, body: str) -> Path:
        (tmp_path / "p.yaml").write_text(body, encoding="utf-8")
        return tmp_path

    BASE = (
        "rules:\n  - rule_id: r1\n    jurisdiction: CN\n    topic: t\n    version: '1'\n"
        "    valid_from: 2024-01-01\n    source_url: https://x.example/\n"
        "    source_title: s\n    evidence_level: secondary\n    verified: false\n"
        "    summary: s\n    content: {}\n"
    )

    def test_valid_minimal_pack_loads(self, tmp_path):
        assert len(load_rule_pack(self._pack(tmp_path, self.BASE))) == 1

    def test_missing_source_url_rejected(self, tmp_path):
        body = self.BASE.replace("    source_url: https://x.example/\n", "")
        with pytest.raises(RulePackError, match="missing keys"):
            load_rule_pack(self._pack(tmp_path, body))

    def test_non_http_source_rejected(self, tmp_path):
        with pytest.raises(RulePackError, match="http"):
            load_rule_pack(self._pack(tmp_path, self.BASE.replace("https://x.example/", "ftp://x")))

    def test_verified_without_primary_rejected(self, tmp_path):
        with pytest.raises(RulePackError, match="primary"):
            body = self.BASE.replace("verified: false", "verified: true")
            load_rule_pack(self._pack(tmp_path, body))

    def test_bad_evidence_level_rejected(self, tmp_path):
        with pytest.raises(RulePackError, match="evidence_level"):
            load_rule_pack(self._pack(tmp_path, self.BASE.replace("secondary", "rumour")))

    def test_duplicate_rule_version_rejected(self, tmp_path):
        two = self.BASE + self.BASE.split("rules:\n", 1)[1]
        with pytest.raises(RulePackError, match="duplicate"):
            load_rule_pack(self._pack(tmp_path, two))

    def test_inverted_validity_rejected(self, tmp_path):
        body = self.BASE.replace("    summary: s", "    valid_to: 2023-01-01\n    summary: s")
        with pytest.raises(RulePackError, match="valid_to"):
            load_rule_pack(self._pack(tmp_path, body))

    def test_empty_directory_rejected(self, tmp_path):
        with pytest.raises(RulePackError, match="no rule packs"):
            load_rule_pack(tmp_path)
