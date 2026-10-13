"""Hash-chained audit event types and the sink interface.

Rule 0.7: everything is audited, via hooks — never inside node code.
Chain rule (M1): `hash = sha256(prev_hash + canonical_json(event))` with a
per-tenant genesis of the zero hash.
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.calc.money import canonical_json, sha256_hex

GENESIS = "0" * 64


class AuditEvent(BaseModel):
    kind: str  # node_started | node_finished | tool_called | tool_refused | ...
    deal_id: str = ""
    tenant_id: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def chain(self, prev_hash: str) -> str:
        """This event's hash given the previous event's hash."""
        body = {
            "kind": self.kind,
            "deal_id": self.deal_id,
            "tenant_id": self.tenant_id,
            "payload": self.payload,
            "ts": self.ts,
        }
        return sha256_hex(prev_hash + canonical_json(body))


class AuditSink(abc.ABC):
    """Where audit events go. The in-memory sink is for tests; the DB sink
    appends to the `audit_event` table (append-only, M1)."""

    @abc.abstractmethod
    def emit(self, event: AuditEvent) -> str:
        """Store the event, return its chain hash."""

    @abc.abstractmethod
    def head(self, tenant_id: str) -> str:
        """Current chain head hash for a tenant."""


class InMemoryAuditSink(AuditSink):
    """Test sink that maintains the same hash chain semantics as the DB."""

    def __init__(self) -> None:
        self.events: list[tuple[AuditEvent, str]] = []
        self._heads: dict[str, str] = {}

    def emit(self, event: AuditEvent) -> str:
        prev = self._heads.get(event.tenant_id, GENESIS)
        h = event.chain(prev)
        self.events.append((event, h))
        self._heads[event.tenant_id] = h
        return h

    def head(self, tenant_id: str) -> str:
        return self._heads.get(tenant_id, GENESIS)

    def verify_chain(self, tenant_id: str) -> bool:
        prev = GENESIS
        for event, h in self.events:
            if event.tenant_id != tenant_id:
                continue
            if event.chain(prev) != h:
                return False
            prev = h
        return True
