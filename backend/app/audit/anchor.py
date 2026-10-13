"""Chain-head anchoring interface (BUILD_PLAN M1).

`AnchorClient` batches the current audit-chain head onto an immutable ledger.
Demo uses `MockAnchor` (in-process, deterministic); `FiscoBcosAnchor` talks to a
local FISCO BCOS node. `execute` is the only node allowed to trigger anchoring
(via the `anchor_hash` tool, rule 0.5).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.calc.money import canonical_json, sha256_hex


@dataclass(frozen=True)
class AnchorReceipt:
    anchor_id: str
    chain_head: str
    tx_ref: str
    anchored_at: str
    mocked: bool


class AnchorClient(abc.ABC):
    @abc.abstractmethod
    def anchor(self, chain_head: str, tenant_id: str) -> AnchorReceipt:
        """Anchor one chain-head hash; must be idempotent per (tenant, head)."""


class MockAnchor(AnchorClient):
    """Deterministic demo anchor: tx_ref derived from the head hash so replays
    return the same receipt (idempotency without external state)."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], AnchorReceipt] = {}

    def anchor(self, chain_head: str, tenant_id: str) -> AnchorReceipt:
        key = (tenant_id, chain_head)
        if key not in self._seen:
            self._seen[key] = AnchorReceipt(
                anchor_id=f"anchor_{len(self._seen) + 1:06d}",
                chain_head=chain_head,
                tx_ref=f"mock-tx-{sha256_hex(canonical_json([tenant_id, chain_head]))[:16]}",
                anchored_at=datetime.now(UTC).isoformat(),
                mocked=True,
            )
        return self._seen[key]


@dataclass
class FiscoBcosAnchor(AnchorClient):
    """Real anchor against a local FISCO BCOS node's JSON-RPC (demo: group 1).
    Disabled unless endpoint configured — the graph falls back to escalation,
    never silently to the mock."""

    endpoint: str
    group_id: int = 1
    contract: str = "AuditAnchor"
    _http: object = field(default=None, repr=False)

    def anchor(self, chain_head: str, tenant_id: str) -> AnchorReceipt:
        import httpx  # local import: only needed when a real anchor is wired

        resp = httpx.post(
            self.endpoint,
            json={
                "group_id": self.group_id,
                "contract": self.contract,
                "method": "anchor",
                "args": [tenant_id, chain_head],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        body = resp.json()
        return AnchorReceipt(
            anchor_id=body["anchor_id"],
            chain_head=chain_head,
            tx_ref=body["tx_ref"],
            anchored_at=datetime.now(UTC).isoformat(),
            mocked=False,
        )
