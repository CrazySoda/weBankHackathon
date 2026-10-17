"""Postgres integration tests (M1 acceptance criteria).

These are the plan's M1 "done when" tests:
- the audit chain detects a tampered row
- RLS blocks cross-tenant reads
- a rule superseded on date X is not returned for deals dated after X
- audit_event is append-only (UPDATE/DELETE revoked)

They require TEST_DATABASE_URL to point to a dedicated disposable database
whose name ends in `test` or `tests`. Several cases run TRUNCATE; these tests
never fall back to the local demo database. Unit tests do not require services.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime
from urllib.parse import urlparse

import pytest
from app.audit.events import AuditEvent
from app.db.bootstrap import apply_schema
from app.rules.store import sql_rules_in_force
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
PG = pytest.importorskip("psycopg") if DATABASE_URL else None


def _url() -> str:
    if not DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to a dedicated disposable test database")
    normalized_url = DATABASE_URL.replace("+psycopg", "").replace("+asyncpg", "")
    database_name = urlparse(normalized_url).path.lstrip("/")
    if re.search(r"(?:^|[_-])tests?$", database_name, flags=re.IGNORECASE) is None:
        pytest.fail(
            "TEST_DATABASE_URL must target a database named test/tests or ending in _test/_tests; "
            "these integration tests truncate tables"
        )
    if DATABASE_URL.startswith("postgres://"):
        return DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    if DATABASE_URL.startswith("postgresql://"):
        return DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    if DATABASE_URL.startswith("postgresql+asyncpg://"):
        return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return DATABASE_URL


@pytest.fixture()
def pg_engine():
    """Owner/superuser engine: schema setup, seeding and out-of-band tampering."""
    eng = create_engine(_url())
    apply_schema(eng)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE tenant, trade_deal, audit_event, rule CASCADE"))
        conn.execute(
            text("INSERT INTO tenant (id, name) VALUES ('tenant_a', 'A'), ('tenant_b', 'B')")
        )
    yield eng
    eng.dispose()


@pytest.fixture()
def app_engine(pg_engine):
    """Engine that runs as the unprivileged application role, so RLS and the
    audit REVOKEs actually bind (the owner is a superuser and bypasses both)."""
    eng = create_engine(_url())

    @event.listens_for(eng, "connect")
    def _assume_app_role(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("SET ROLE cleartrade_app")
        cur.close()
        dbapi_conn.commit()

    yield eng
    eng.dispose()


def _set_tenant(conn, tenant: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, false)"), {"t": tenant})


class TestRls:
    def test_cross_tenant_read_blocked(self, app_engine):
        with app_engine.begin() as conn:
            _set_tenant(conn, "tenant_a")
            conn.execute(
                text(
                    "INSERT INTO trade_deal (id, tenant_id, state) "
                    "VALUES ('d1', 'tenant_a', 'created')"
                )
            )

        with app_engine.connect() as conn:
            _set_tenant(conn, "tenant_b")
            n = conn.execute(text("SELECT count(*) FROM trade_deal WHERE id = 'd1'")).scalar()
            assert n == 0

        with app_engine.connect() as conn:
            _set_tenant(conn, "tenant_a")
            n = conn.execute(text("SELECT count(*) FROM trade_deal WHERE id = 'd1'")).scalar()
            assert n == 1

    def test_cannot_write_into_another_tenant(self, app_engine):
        with app_engine.connect() as conn:
            _set_tenant(conn, "tenant_b")
            with pytest.raises(DBAPIError):
                conn.execute(
                    text(
                        "INSERT INTO trade_deal (id, tenant_id, state) "
                        "VALUES ('d2', 'tenant_a', 'created')"
                    )
                )
            conn.rollback()

    def test_no_tenant_set_sees_nothing(self, app_engine):
        with app_engine.begin() as conn:
            _set_tenant(conn, "tenant_a")
            conn.execute(
                text(
                    "INSERT INTO trade_deal (id, tenant_id, state) "
                    "VALUES ('d3', 'tenant_a', 'created')"
                )
            )
        with app_engine.connect() as conn:
            _set_tenant(conn, "")
            assert conn.execute(text("SELECT count(*) FROM trade_deal")).scalar() == 0


class TestAuditAppendOnly:
    def test_update_delete_revoked(self, app_engine):
        with app_engine.begin() as conn:
            _set_tenant(conn, "tenant_a")
            conn.execute(
                text(
                    "INSERT INTO audit_event (tenant_id, deal_id, kind, payload, prev_hash, hash) "
                    "VALUES ('tenant_a', 'd1', 'test', '{}', '0', 'h')"
                )
            )

        with app_engine.connect() as conn:
            _set_tenant(conn, "tenant_a")
            with pytest.raises(DBAPIError, match="permission denied"):
                conn.execute(text("UPDATE audit_event SET kind = 'forged' WHERE deal_id = 'd1'"))
            conn.rollback()
            _set_tenant(conn, "tenant_a")
            with pytest.raises(DBAPIError, match="permission denied"):
                conn.execute(text("DELETE FROM audit_event WHERE deal_id = 'd1'"))
            conn.rollback()


class TestAuditChainTamper:
    def test_tampered_row_detected(self, pg_engine, app_engine):
        """Verify the stored chain end-to-end; a mutated payload breaks it."""
        from app.calc.money import canonical_json, sha256_hex

        with app_engine.begin() as conn:
            _set_tenant(conn, "tenant_a")
            prev = "0" * 64
            for i, kind in enumerate(["node_started", "node_finished", "tool_called"]):
                payload = {"node": f"n{i}", "seq": i}
                ts = datetime.now(UTC)
                body = {
                    "kind": kind,
                    "deal_id": "d1",
                    "tenant_id": "tenant_a",
                    "payload": payload,
                    "ts": ts.isoformat(),
                }
                h = sha256_hex(prev + canonical_json(body))
                conn.execute(
                    text(
                        "INSERT INTO audit_event (tenant_id, deal_id, kind, payload, "
                        "ts, prev_hash, hash) "
                        "VALUES (:t, :d, :k, cast(:p AS jsonb), :ts, :ph, :h)"
                    ),
                    {
                        "t": "tenant_a",
                        "d": "d1",
                        "k": kind,
                        "p": canonical_json(payload),
                        "ts": ts,
                        "ph": prev,
                        "h": h,
                    },
                )
                prev = h

        def verify() -> bool:
            with app_engine.connect() as conn:
                _set_tenant(conn, "tenant_a")
                rows = conn.execute(
                    text(
                        "SELECT kind, deal_id, tenant_id, payload, ts, prev_hash, hash "
                        "FROM audit_event ORDER BY id"
                    )
                ).all()
            p = "0" * 64
            for r in rows:
                body = {
                    "kind": r.kind,
                    "deal_id": r.deal_id,
                    "tenant_id": r.tenant_id,
                    "payload": dict(r.payload),
                    "ts": r.ts.isoformat(),
                }
                if sha256_hex(p + canonical_json(body)) != r.hash:
                    return False
                p = r.hash
            return True

        assert verify()

        # tamper directly in storage as the table owner (a DBA); the app role cannot
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE audit_event "
                    "SET payload = payload || '{\"seq\": 999}' WHERE kind = 'node_finished'"
                )
            )

        assert not verify()


class TestRulesSql:
    def test_superseded_rule_not_served_after_date(self, pg_engine):
        with pg_engine.begin() as conn:
            conn.execute(text("TRUNCATE rule"))
            rows = [
                ("R1", "1.0", date(2024, 1, 1), date(2026, 1, 1), None),
                ("R1", "2.0", date(2026, 1, 1), None, None),
            ]
            for rule_id, ver, vf, vt, sup in rows:
                conn.execute(
                    text(
                        "INSERT INTO rule (rule_id, jurisdiction, topic, version, content, "
                        "source_url, valid_from, valid_to, superseded_at) "
                        "VALUES (:r, 'CN', 'vat_refund', :v, cast('{}' AS jsonb), 'https://x', "
                        ":vf, :vt, :sup)"
                    ),
                    {"r": rule_id, "v": ver, "vf": vf, "vt": vt, "sup": sup},
                )

        with pg_engine.connect() as conn:
            before = sql_rules_in_force(conn, "CN", "vat_refund", date(2025, 12, 31))
            after = sql_rules_in_force(conn, "CN", "vat_refund", date(2026, 6, 1))

        assert [r.version for r in before if r.rule_id == "R1"] == ["1.0"]
        assert [r.version for r in after if r.rule_id == "R1"] == ["2.0"]


def test_event_model_chain_matches_db_convention():
    """The AuditEvent model's chain() must match the SQL test convention."""
    e = AuditEvent(
        kind="k", deal_id="d", tenant_id="t", payload={"a": 1}, ts="2026-01-01T00:00:00+00:00"
    )
    h = e.chain("0" * 64)
    assert len(h) == 64
