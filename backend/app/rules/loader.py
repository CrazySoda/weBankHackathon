"""Load the curated rule pack from ``seed/rules/*.yaml`` into ``RuleRow`` s.

Rule content is curated, never generated at runtime (BUILD_PLAN section 7).
Every rule must carry a source URL and an honest ``evidence_level``; anything
not confirmed from a primary source stays ``verified: false`` so the UI and the
reviewer can see which rules still need a human check.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.rules.store import RuleRow

DEFAULT_RULES_DIR = Path(__file__).resolve().parents[2] / "seed" / "rules"

# Fixed system time keeps loads deterministic and reproducible.
# DECISION: curated seed rules are recorded at a constant instant, not "now".
SEED_RECORDED_AT = datetime(2026, 10, 15, tzinfo=UTC)

EVIDENCE_LEVELS = frozenset({"primary", "secondary", "none"})
REQUIRED_KEYS = (
    "rule_id",
    "jurisdiction",
    "topic",
    "version",
    "valid_from",
    "source_url",
    "source_title",
    "evidence_level",
    "verified",
    "summary",
    "content",
)


class RulePackError(ValueError):
    """The rule pack is malformed; callers must fail closed."""


def _as_date(value: Any, where: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise RulePackError(f"{where}: expected a calendar date, got {value!r}")
    return value


def _row(raw: dict[str, Any], origin: str) -> RuleRow:
    where = f"{origin}:{raw.get('rule_id', '?')}"
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise RulePackError(f"{where}: missing keys {missing}")
    if not str(raw["source_url"]).startswith(("http://", "https://")):
        raise RulePackError(f"{where}: source_url must be http(s)")
    if raw["evidence_level"] not in EVIDENCE_LEVELS:
        raise RulePackError(f"{where}: bad evidence_level {raw['evidence_level']!r}")
    if not isinstance(raw["verified"], bool):
        raise RulePackError(f"{where}: verified must be a bool")
    if raw["verified"] and raw["evidence_level"] != "primary":
        raise RulePackError(f"{where}: only primary-sourced rules may be verified")
    if raw.get("demo_assumption") and raw["verified"]:
        raise RulePackError(f"{where}: a demo assumption cannot be verified")
    if not isinstance(raw["content"], dict):
        raise RulePackError(f"{where}: content must be a mapping")
    valid_from = _as_date(raw["valid_from"], where)
    valid_to = _as_date(raw["valid_to"], where) if raw.get("valid_to") is not None else None
    if valid_to is not None and valid_to <= valid_from:
        raise RulePackError(f"{where}: valid_to must be after valid_from")

    meta = {
        "summary": raw["summary"],
        "source_title": raw["source_title"],
        "evidence_level": raw["evidence_level"],
        "verified": raw["verified"],
        "demo_assumption": bool(raw.get("demo_assumption", False)),
        "valid_from_precision": raw.get("valid_from_precision", "exact"),
    }
    return RuleRow(
        rule_id=str(raw["rule_id"]),
        jurisdiction=str(raw["jurisdiction"]),
        topic=str(raw["topic"]),
        version=str(raw["version"]),
        content={**raw["content"], "_meta": meta},
        source_url=str(raw["source_url"]),
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=SEED_RECORDED_AT,
    )


def load_rule_pack(rules_dir: Path | str = DEFAULT_RULES_DIR) -> list[RuleRow]:
    """Parse and validate every ``*.yaml`` pack; raise ``RulePackError`` on any flaw."""
    import yaml

    directory = Path(rules_dir)
    files = sorted(directory.glob("*.yaml"))
    if not files:
        raise RulePackError(f"no rule packs found in {directory}")
    rows: list[RuleRow] = []
    seen: set[tuple[str, str]] = set()
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            raise RulePackError(f"{path.name}: expected a mapping with a 'rules' list")
        for raw in data["rules"]:
            if not isinstance(raw, dict):
                raise RulePackError(f"{path.name}: each rule must be a mapping")
            row = _row(raw, path.name)
            key = (row.rule_id, row.version)
            if key in seen:
                raise RulePackError(f"duplicate rule {row.rule_id} version {row.version}")
            seen.add(key)
            rows.append(row)
    return rows


def unverified_rule_ids(rows: list[RuleRow]) -> list[str]:
    """Rules a human must still confirm against a primary source."""
    return sorted({r.rule_id for r in rows if not r.content["_meta"]["verified"]})
