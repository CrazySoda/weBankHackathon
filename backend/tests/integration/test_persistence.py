"""Durable deals: snapshots, the audit chain and graph checkpoints survive a restart.

Needs TEST_DATABASE_URL (a disposable `*_test` database), like test_db.py. A "restart"
is a second DealRunner/DealStore built against the same database.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

import fakeredis
import pytest
from app.api.deals import DealRunner
from app.audit.events import AuditEvent
from app.config import Settings
from app.db.bootstrap import apply_schema
from app.db.persistence import DealStore
from app.graph.nodes.extract_doc import ExtractionOutput
from app.graph.state import DealState
from app.harness.budget import DealBudget
from app.security.storage import DocumentStore
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import create_engine, text

from tests.api.test_api import INV_FIELDS, LC_FIELDS
from tests.graph.conftest import FakeLLM, make_pdf, sign_for
from tests.integration.test_db import _url

pytestmark = pytest.mark.integration

TENANT = "demo-tenant"


@pytest.fixture(scope="module")
def event_loop_policy():
    """psycopg's async mode (the LangGraph Postgres checkpointer) cannot run on
    Windows' default Proactor loop; the Linux container the backend ships in is fine."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture()
def pg_url():
    url = _url()
    eng = create_engine(url)
    apply_schema(eng)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE audit_event, deal_snapshot"))
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                conn.execute(text(f"TRUNCATE {table}"))
    yield url
    eng.dispose()


def _event(n: int, deal: str = "d1", tenant: str = TENANT) -> AuditEvent:
    return AuditEvent(kind="node_finished", deal_id=deal, tenant_id=tenant, payload={"n": n})


class TestAuditChain:
    def test_chain_persists_across_store_instances_and_verifies(self, pg_url):
        first = DealStore(pg_url)
        for n in range(3):
            first.audit.emit(_event(n))
        head = first.audit.head(TENANT)

        restarted = DealStore(pg_url)  # a new process: no in-memory head to lean on
        assert restarted.audit.head(TENANT) == head
        restarted.audit.emit(_event(3))
        assert restarted.audit.verify_chain(TENANT)
        assert [e.payload["n"] for e, _ in restarted.audit.trail("d1", TENANT)] == [0, 1, 2, 3]

    def test_a_tampered_row_breaks_the_chain(self, pg_url):
        store = DealStore(pg_url)
        for n in range(3):
            store.audit.emit(_event(n))
        owner = create_engine(pg_url)  # only the owner can write past the REVOKEs
        with owner.begin() as conn:
            conn.execute(
                text(
                    "UPDATE audit_event SET payload = '{\"n\": 99}' WHERE id = "
                    "(SELECT min(id) FROM audit_event)"
                )
            )
        owner.dispose()
        assert store.audit.verify_chain(TENANT) is False

    def test_trail_is_tenant_scoped(self, pg_url):
        store = DealStore(pg_url)
        store.audit.emit(_event(0, deal="d1", tenant="tenant_a"))
        assert store.audit.trail("d1", "tenant_a")
        assert store.audit.trail("d1", "tenant_b") == []


class TestSnapshots:
    def test_roundtrip_and_tenant_isolation(self, pg_url):
        store = DealStore(pg_url)
        state = DealState(deal_id="deal_x", tenant_id="tenant_a")
        budget = DealBudget("deal_x", max_steps=10, max_tokens=10, max_cost_minor=10)
        budget.steps = 4
        store.save(state, budget)

        loaded = store.load("deal_x", "tenant_a")
        assert loaded is not None
        assert loaded[0] == state
        assert loaded[1]["steps"] == 4
        assert store.load("deal_x", "tenant_b") is None  # RLS: another tenant sees nothing


def _settings(url: str, owner_key: ed25519.Ed25519PrivateKey) -> Settings:
    pub = owner_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return Settings(
        litellm_virtual_key="sk-test",
        approval_signing_key="k",
        approval_public_keys_json=json.dumps({"owner": base64.b64encode(pub).decode()}),
        persist_deals=True,
        sync_database_url=url,
    )


def _runner(url: str, owner_key, tmp_path: Path) -> DealRunner:
    runner = DealRunner(_settings(url, owner_key), DocumentStore(tmp_path / "docs"), DealStore(url))
    fake = FakeLLM()

    def hint(messages):
        c = messages[-1]["content"]
        if "letter_of_credit" in c:
            return ExtractionOutput(kind="letter_of_credit", fields=LC_FIELDS)
        if "commercial_invoice" in c:
            return ExtractionOutput(kind="commercial_invoice", fields=INV_FIELDS)
        return ExtractionOutput(kind="unknown", fields=[])

    fake.hooks["ExtractionOutput"] = hint
    runner.llm = fake  # type: ignore[assignment]
    runner.idempotency = fakeredis.FakeRedis(decode_responses=True)
    return runner


class TestRestart:
    def test_deal_audit_and_budget_rehydrate(self, pg_url, tmp_path):
        key = ed25519.Ed25519PrivateKey.generate()
        before = _runner(pg_url, key, tmp_path)
        deal_id = before.create_deal(TENANT).state.deal_id
        pdf = make_pdf(["LETTER OF CREDIT USD 100,000.00"])
        before.add_document(deal_id, pdf, "lc.pdf", "application/pdf", "letter_of_credit")
        before.deals[deal_id].budget.steps = 7
        before._persist(deal_id)
        trail = before.audit_trail(deal_id)

        after = _runner(pg_url, key, tmp_path)  # restart
        assert deal_id in after.deals
        rec = after.deals[deal_id]
        assert [d.filename for d in rec.state.documents] == ["lc.pdf"]
        assert rec.budget.steps == 7  # a restart cannot reset the kill-switch counters
        assert after.audit_trail(deal_id) == trail
        assert after.audit.verify_chain(TENANT)
        assert "nope" not in after.deals

    @pytest.mark.asyncio
    async def test_parked_approval_can_be_signed_and_executed_after_restart(self, pg_url, tmp_path):
        key = ed25519.Ed25519PrivateKey.generate()
        before = _runner(pg_url, key, tmp_path)
        await before.start()
        deal_id = before.create_deal(TENANT).state.deal_id
        for name, kind, line in (
            ("lc.pdf", "letter_of_credit", "LETTER OF CREDIT USD 100,000.00"),
            ("inv.pdf", "commercial_invoice", "COMMERCIAL INVOICE USD 100,000.00"),
        ):
            before.add_document(deal_id, make_pdf([line]), name, "application/pdf", kind)
        await before.run(deal_id)

        queue = before.deals[deal_id].queue
        interrupt = None
        while not queue.empty():
            event = queue.get_nowait()
            if (
                event.get("type") == "interrupt"
                and event["payload"].get("kind") == "human_approval"
            ):
                interrupt = event["payload"]
        assert interrupt is not None, "deal should be parked at human approval"
        approval = sign_for(interrupt, key)
        await before.stop()

        after = _runner(pg_url, key, tmp_path)  # restart: new runner, new checkpointer pool
        await after.start()
        try:
            await after.resume(deal_id, {"action": "approve", "approval": approval})
            state = after.deals[deal_id].state
            assert state.receipt is not None
            assert state.receipt.amount.minor == 10_000_000
            assert after.audit.verify_chain(TENANT)
        finally:
            await after.stop()
