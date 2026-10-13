"""Bitemporal rule store (BUILD_PLAN M1).

`rules_in_force(jurisdiction, topic, as_of)` returns the rules in force on a
deal date, honouring BOTH time dimensions:

- event time:  valid_from <= as_of < (valid_to or +inf)
- system time: the row with the latest recorded_at per rule_id whose record has
  not been superseded

Rule content is curated in `seed/rules/` (never generated at runtime). The pure
selector works on any list of RuleRows (tests use SQLite/in-memory); the SQL
query in `sql_rules_in_force` is the Postgres path.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class RuleRow:
    rule_id: str
    jurisdiction: str
    topic: str
    version: str
    content: dict[str, Any]
    source_url: str
    valid_from: date
    valid_to: date | None  # None = still valid at the far end
    recorded_at: datetime
    superseded_at: datetime | None = None


def rules_in_force(
    rows: list[RuleRow], jurisdiction: str, topic: str, as_of: date
) -> list[RuleRow]:
    """Pure bitemporal selector. Deterministic order: rule_id, then version."""
    latest_by_rule: dict[str, RuleRow] = {}
    for r in rows:
        if r.jurisdiction != jurisdiction or r.topic != topic:
            continue
        if not (r.valid_from <= as_of and (r.valid_to is None or as_of < r.valid_to)):
            continue
        if r.superseded_at is not None:
            continue
        cur = latest_by_rule.get(r.rule_id)
        if cur is None or r.recorded_at > cur.recorded_at:
            latest_by_rule[r.rule_id] = r
    return sorted(latest_by_rule.values(), key=lambda r: (r.rule_id, r.version))


SQL_RULES_IN_FORCE = text("""
    SELECT DISTINCT ON (rule_id)
           rule_id, jurisdiction, topic, version, content, source_url,
           valid_from, valid_to, recorded_at, superseded_at
    FROM rule
    WHERE jurisdiction = :jurisdiction
      AND topic = :topic
      AND valid_from <= :as_of
      AND (valid_to IS NULL OR :as_of < valid_to)
      AND superseded_at IS NULL
    ORDER BY rule_id, recorded_at DESC
""")


def sql_rules_in_force(
    conn: Connection, jurisdiction: str, topic: str, as_of: date
) -> list[RuleRow]:
    result = conn.execute(
        SQL_RULES_IN_FORCE, {"jurisdiction": jurisdiction, "topic": topic, "as_of": as_of}
    )
    return [
        RuleRow(
            rule_id=row.rule_id,
            jurisdiction=row.jurisdiction,
            topic=row.topic,
            version=row.version,
            content=row.content,
            source_url=row.source_url,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            recorded_at=row.recorded_at,
            superseded_at=row.superseded_at,
        )
        for row in result
    ]


class RuleStore(abc.ABC):
    """Node-facing read API; implementations resolve via the selector above."""

    @abc.abstractmethod
    def in_force(self, jurisdiction: str, topic: str, as_of: date) -> list[RuleRow]: ...
