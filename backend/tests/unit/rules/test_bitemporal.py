"""Bitemporal rule selector tests: a rule superseded on date X is not returned
for deals dated after X (M1 acceptance)."""

from datetime import UTC, date, datetime

from app.rules.store import RuleRow, rules_in_force


def ts(y: int, m: int, d: int, hh: int = 0) -> datetime:
    return datetime(y, m, d, hh, tzinfo=UTC)


def row(
    rule_id: str,
    version: str,
    vf: date,
    vt: date | None,
    recorded: datetime,
    superseded: datetime | None = None,
    jurisdiction: str = "CN",
    topic: str = "vat_refund",
) -> RuleRow:
    return RuleRow(
        rule_id=rule_id,
        jurisdiction=jurisdiction,
        topic=topic,
        version=version,
        content={"rebate_rate_bp": 1300},
        source_url="https://example.com/rule",
        valid_from=vf,
        valid_to=vt,
        recorded_at=recorded,
        superseded_at=superseded,
    )


ROWS = [
    # v1 of R1: valid 2024-01-01 → 2025-12-31, recorded 2024-01-01
    row("R1", "1.0", date(2024, 1, 1), date(2026, 1, 1), ts(2024, 1, 1)),
    # v2 of R1: valid from 2026-01-01, recorded later
    row("R1", "2.0", date(2026, 1, 1), None, ts(2025, 12, 1)),
    # R2: open-ended, later corrected (v2 recorded after v1, both same validity)
    row("R2", "1.0", date(2020, 1, 1), None, ts(2020, 1, 1)),
    row("R2", "1.1", date(2020, 1, 1), None, ts(2025, 6, 1)),
    # R3: superseded correction — recorded 2026-02-01 but superseded; must never show
    row("R3", "9.9", date(2020, 1, 1), None, ts(2026, 2, 1), superseded=ts(2026, 2, 2)),
    row("R3", "1.0", date(2020, 1, 1), None, ts(2020, 1, 1)),
    # R4: wrong jurisdiction / topic filters
    row("R4", "1.0", date(2020, 1, 1), None, ts(2020, 1, 1), jurisdiction="BD"),
    row("R5", "1.0", date(2020, 1, 1), None, ts(2020, 1, 1), topic="ucp600"),
]


class TestRulesInForce:
    def test_version_switch_at_validity_boundary(self):
        out = rules_in_force(ROWS, "CN", "vat_refund", date(2025, 12, 31))
        r1 = next(r for r in out if r.rule_id == "R1")
        assert r1.version == "1.0"

        out2 = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 1, 1))
        r1b = next(r for r in out2 if r.rule_id == "R1")
        assert r1b.version == "2.0"

    def test_superseded_on_date_x_not_returned_after(self):
        out = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 10, 13))
        assert not any(r.rule_id == "R3" and r.version == "9.9" for r in out)
        r3 = next(r for r in out if r.rule_id == "R3")
        assert r3.version == "1.0"

    def test_latest_correction_wins(self):
        out = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 6, 1))
        r2 = next(r for r in out if r.rule_id == "R2")
        assert r2.version == "1.1"

    def test_jurisdiction_and_topic_filters(self):
        out = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 6, 1))
        ids = {r.rule_id for r in out}
        assert "R4" not in ids  # BD jurisdiction
        assert "R5" not in ids  # different topic

    def test_deterministic_order(self):
        a = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 6, 1))
        b = rules_in_force(ROWS, "CN", "vat_refund", date(2026, 6, 1))
        assert [r.rule_id for r in a] == [r.rule_id for r in b]
        assert [r.rule_id for r in a] == sorted(r.rule_id for r in a)

    def test_empty_for_unknown_topic(self):
        assert rules_in_force(ROWS, "CN", "nope", date(2026, 6, 1)) == []
