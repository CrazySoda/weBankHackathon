"""Postgres persistence for the deal runner: deal snapshots + the hash-chained audit log.

Everything here runs as the unprivileged ``cleartrade_app`` role (see
``app.db.bootstrap.app_role_engine``) with ``app.current_tenant`` set per transaction,
so row-level security and the append-only audit grants bind for real.

The audit chain is the same one the in-memory sink keeps
(``hash = sha256(prev_hash + canonical_json(event))``); ``emit`` reads the tenant's
head and inserts under a per-tenant advisory lock so concurrent writers cannot fork it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from app.audit.events import GENESIS, AuditEvent, AuditSink
from app.db.bootstrap import app_role_engine, apply_schema
from app.graph.state import DealState
from app.harness.budget import DealBudget

_BUDGET_FIELDS = ("steps", "tokens", "cost_minor", "killed", "kill_reason")


def _scope(conn: Connection, tenant_id: str) -> None:
    """Bind this transaction to one tenant (RLS key); cleared when it ends."""
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})


def _event_from_row(row: Any) -> AuditEvent:
    return AuditEvent(
        kind=row.kind,
        deal_id=row.deal_id,
        tenant_id=row.tenant_id,
        payload=row.payload,
        ts=row.ts.astimezone(UTC).isoformat(),
    )


class PostgresAuditChain(AuditSink):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def emit(self, event: AuditEvent) -> str:
        with self._engine.begin() as conn:
            _scope(conn, event.tenant_id)
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": event.tenant_id})
            prev = self._head(conn, event.tenant_id)
            h = event.chain(prev)
            conn.execute(
                text(
                    "INSERT INTO audit_event "
                    "(tenant_id, deal_id, kind, payload, ts, prev_hash, hash) "
                    "VALUES (:tenant, :deal, :kind, CAST(:payload AS jsonb), :ts, :prev, :hash)"
                ),
                {
                    "tenant": event.tenant_id,
                    "deal": event.deal_id,
                    "kind": event.kind,
                    "payload": json.dumps(event.payload, default=str),
                    "ts": datetime.fromisoformat(event.ts),
                    "prev": prev,
                    "hash": h,
                },
            )
        return h

    @staticmethod
    def _head(conn: Connection, tenant_id: str) -> str:
        head = conn.execute(
            text("SELECT hash FROM audit_event WHERE tenant_id = :t ORDER BY id DESC LIMIT 1"),
            {"t": tenant_id},
        ).scalar()
        return head or GENESIS

    def head(self, tenant_id: str) -> str:
        with self._engine.begin() as conn:
            _scope(conn, tenant_id)
            return self._head(conn, tenant_id)

    def verify_chain(self, tenant_id: str) -> bool:
        with self._engine.begin() as conn:
            _scope(conn, tenant_id)
            rows = conn.execute(
                text(
                    "SELECT kind, deal_id, tenant_id, payload, ts, hash "
                    "FROM audit_event WHERE tenant_id = :t ORDER BY id"
                ),
                {"t": tenant_id},
            ).all()
        prev = GENESIS
        for row in rows:
            if _event_from_row(row).chain(prev) != row.hash:
                return False
            prev = row.hash
        return True

    def trail(self, deal_id: str, tenant_id: str) -> list[tuple[AuditEvent, str]]:
        with self._engine.begin() as conn:
            _scope(conn, tenant_id)
            rows = conn.execute(
                text(
                    "SELECT kind, deal_id, tenant_id, payload, ts, hash "
                    "FROM audit_event WHERE deal_id = :d ORDER BY id"
                ),
                {"d": deal_id},
            ).all()
        return [(_event_from_row(r), r.hash) for r in rows]


class DealStore:
    """Deal snapshots and the audit chain, in Postgres."""

    def __init__(self, sync_url: str) -> None:
        owner = create_engine(sync_url)
        try:
            apply_schema(owner)  # tables + RLS + grants; idempotent
        finally:
            owner.dispose()
        self.engine = app_role_engine(sync_url)
        self.audit = PostgresAuditChain(self.engine)

    def save(self, state: DealState, budget: DealBudget) -> None:
        with self.engine.begin() as conn:
            _scope(conn, state.tenant_id)
            conn.execute(
                text(
                    "INSERT INTO deal_snapshot (deal_id, tenant_id, state, budget) "
                    "VALUES (:d, :t, CAST(:s AS jsonb), CAST(:b AS jsonb)) "
                    "ON CONFLICT (deal_id) DO UPDATE "
                    "SET state = EXCLUDED.state, budget = EXCLUDED.budget, updated_at = now()"
                ),
                {
                    "d": state.deal_id,
                    "t": state.tenant_id,
                    "s": json.dumps(state.model_dump(mode="json")),
                    "b": json.dumps({k: getattr(budget, k) for k in _BUDGET_FIELDS}),
                },
            )

    def load(self, deal_id: str, tenant_id: str) -> tuple[DealState, dict[str, Any]] | None:
        with self.engine.begin() as conn:
            _scope(conn, tenant_id)
            row = conn.execute(
                text("SELECT state, budget FROM deal_snapshot WHERE deal_id = :d"),
                {"d": deal_id},
            ).first()
        if row is None:
            return None
        return DealState.model_validate(row.state), row.budget
