"""Deal runner service: owns compiled graphs per deal, streams events.

Two modes. Without a ``DealStore`` (tests, bare uvicorn) everything is in memory.
With one (``PERSIST_DEALS=true``), deal snapshots and the hash-chained audit log live
in Postgres and the graph uses the LangGraph Postgres checkpointer, so a restart
loses nothing: a deal parked at approval can still be resumed. Per-deal asyncio
queues for SSE stay in memory (live-stream plumbing only).
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.audit.anchor import MockAnchor
from app.audit.events import GENESIS, AuditEvent, AuditSink
from app.config import Settings
from app.db.persistence import DealStore, PostgresAuditChain
from app.graph.build import build_graph
from app.graph.nodes.extract_doc import (
    ALLOWED_KINDS as ALLOWED_DOC_KINDS,
)
from app.graph.nodes.extract_doc import (
    extract_doc as extract_doc_node,
)
from app.graph.state import DealState, DocRef, new_id
from app.harness.budget import DealBudget
from app.harness.hooks import NodeContext, wrap_with_hooks
from app.harness.llm import LLMClient
from app.security.approval import ApprovalVerifier
from app.security.storage import DocumentStore
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from redis import Redis


@dataclass
class DealRecord:
    state: DealState
    budget: DealBudget
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    thread_id: str = ""
    running: bool = False


class _Deals(dict[str, DealRecord]):
    """In-memory cache of deals; a miss rehydrates the deal from the store, so every
    ``in`` / ``[]`` / ``get`` works after a restart without callers knowing."""

    def __init__(self, load: Callable[[str], DealRecord | None]) -> None:
        super().__init__()
        self._load = load

    def __missing__(self, key: str) -> DealRecord:
        rec = self._load(key)
        if rec is None:
            raise KeyError(key)
        self[key] = rec
        return rec

    def __contains__(self, key: object) -> bool:
        return super().__contains__(key) or (isinstance(key, str) and self.get(key) is not None)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class EventfulAuditSink(AuditSink):
    """Forwards every audit event to the deal's SSE queue and keeps the chain
    (in memory, or in Postgres when the runner has a store)."""

    def __init__(self, runner: DealRunner, chain: AuditSink | None = None) -> None:
        self._runner = runner
        self._fallback: Any = chain if chain is not None else InMemoryChainForwarder()

    def emit(self, event: AuditEvent) -> str:
        h: str = self._fallback.emit(event)
        rec = self._runner.deals.get(event.deal_id)
        if rec is not None:
            etype = "interrupt" if event.kind == "node_interrupted" else event.kind
            rec.queue.put_nowait(
                {
                    "type": etype,
                    "node": event.payload.get("node", ""),
                    "ts": event.ts,
                    # interrupt details are attached by the nodes via interrupt()
                    # and live in the langgraph event, not the audit payload;
                    # the UI falls back to fetching deal state for them.
                    "payload": event.payload,
                }
            )
        return h

    def head(self, tenant_id: str) -> str:
        return str(self._fallback.head(tenant_id))

    def verify_chain(self, tenant_id: str) -> bool:
        return bool(self._fallback.verify_chain(tenant_id))

    @property
    def events(self) -> list[tuple[AuditEvent, str]]:
        return list(self._fallback.events)

    def trail(self, deal_id: str, tenant_id: str) -> list[tuple[AuditEvent, str]]:
        if isinstance(self._fallback, PostgresAuditChain):
            return list(self._fallback.trail(deal_id, tenant_id))
        return [(e, h) for e, h in self._fallback.events if e.deal_id == deal_id]


class InMemoryChainForwarder(AuditSink):
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


class DealRunner:
    def __init__(self, settings: Settings, docs: DocumentStore, store: DealStore | None = None):
        self.settings = settings
        self.docs = docs
        self.store = store
        self.deals = _Deals(self._rehydrate)
        self._checkpointers: dict[str, InMemorySaver] = {}
        self._pg_checkpointer: Any = None
        self._pool: Any = None
        self.audit = EventfulAuditSink(self, store.audit if store else None)
        self.anchor = MockAnchor()
        self.idempotency = Redis.from_url(settings.redis_url, decode_responses=True)
        raw_keys = json.loads(settings.approval_public_keys_json)
        if not raw_keys and settings.env == "demo":
            from app.security.approval import DEMO_APPROVER_ID, DEMO_PUBLIC_KEY_B64

            raw_keys = {DEMO_APPROVER_ID: DEMO_PUBLIC_KEY_B64}
        self.approval_verifier = ApprovalVerifier(
            {
                name: Ed25519PublicKey.from_public_bytes(base64.b64decode(value, validate=True))
                for name, value in raw_keys.items()
            }
        )
        self.llm = LLMClient(
            base_url=settings.litellm_base_url,
            api_key=settings.litellm_virtual_key,
            timeout_s=settings.litellm_timeout_s,
        )

    # -- persistence -------------------------------------------------------

    async def start(self) -> None:
        """Open the Postgres checkpointer (no-op without a store)."""
        if self.store is None:
            return
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        # Owner connection: the checkpointer creates its own tables. These hold the
        # graph's working state per thread_id and are not tenant-scoped (DECISIONS #21).
        conninfo = self.settings.sync_database_url.replace("+psycopg", "")
        self._pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await self._pool.open()
        saver = AsyncPostgresSaver(self._pool)
        await saver.setup()
        self._pg_checkpointer = saver

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._pg_checkpointer = None

    def _new_budget(self, deal_id: str) -> DealBudget:
        return DealBudget(
            deal_id,
            max_steps=self.settings.budget_max_steps,
            max_tokens=self.settings.budget_max_tokens_per_deal,
            max_cost_minor=self.settings.budget_max_cost_minor_per_deal,
        )

    def _rehydrate(self, deal_id: str) -> DealRecord | None:
        if self.store is None:
            return None
        loaded = self.store.load(deal_id, self.settings.default_tenant)
        if loaded is None:
            return None
        state, saved_budget = loaded
        budget = self._new_budget(deal_id)
        # restore the spend so a restart cannot reset a deal's kill-switch counters
        for name, value in saved_budget.items():
            setattr(budget, name, value)
        return DealRecord(state=state, budget=budget, thread_id=deal_id)

    def _persist(self, deal_id: str) -> None:
        if self.store is None:
            return
        rec = self.deals[deal_id]
        self.store.save(rec.state, rec.budget)

    # -- lifecycle ---------------------------------------------------------

    def create_deal(self, tenant_id: str, lc_ref: str | None = None) -> DealRecord:
        deal_id = new_id("deal")
        rec = DealRecord(
            state=DealState(deal_id=deal_id, tenant_id=tenant_id),
            budget=self._new_budget(deal_id),
            thread_id=deal_id,
        )
        self.deals[deal_id] = rec
        self._persist(deal_id)
        self.audit.emit(
            AuditEvent(kind="deal_created", deal_id=deal_id, tenant_id=tenant_id, payload={})
        )
        return rec

    def add_document(
        self, deal_id: str, data: bytes, filename: str, mime: str, kind: str = "unknown"
    ) -> DocRef:
        rec = self._require(deal_id)
        sha = self.docs.put(data)
        ref = DocRef(
            doc_id=new_id("doc"),
            deal_id=deal_id,
            sha256=sha,
            filename=filename,
            mime=mime,
            size_bytes=len(data),
            kind=kind if kind in ALLOWED_DOC_KINDS else "unknown",
        )
        rec.state.documents.append(ref)
        self._persist(deal_id)
        self.audit.emit(
            AuditEvent(
                kind="document_registered",
                deal_id=deal_id,
                tenant_id=rec.state.tenant_id,
                payload={"doc_id": ref.doc_id, "sha256": sha, "filename": filename},
            )
        )
        return ref

    def remove_document(self, deal_id: str, doc_id: str) -> DocRef:
        rec = self._require(deal_id)
        if rec.running:
            raise RuntimeError("deal already running")
        if any(
            (
                rec.state.check_plan,
                rec.state.findings,
                rec.state.fx_options,
                rec.state.cash_projection,
                rec.state.finance_offer,
                rec.state.policy,
                rec.state.approval,
                rec.state.receipt,
                rec.state.report_summary,
                rec.state.fatal_error,
                rec.state.escalation_reason,
                rec.state.pending_doc,
            )
        ):
            raise RuntimeError("documents cannot be removed after review has started")
        ref = next((doc for doc in rec.state.documents if doc.doc_id == doc_id), None)
        if ref is None:
            raise KeyError(doc_id)
        rec.state = rec.state.model_copy(
            update={
                "documents": [doc for doc in rec.state.documents if doc.doc_id != doc_id],
                "extracted": [item for item in rec.state.extracted if item.doc_id != doc_id],
                "injection_flags": [
                    flag for flag in rec.state.injection_flags if flag.doc_id != doc_id
                ],
            }
        )
        self._persist(deal_id)
        self.audit.emit(
            AuditEvent(
                kind="document_removed",
                deal_id=deal_id,
                tenant_id=rec.state.tenant_id,
                payload={"doc_id": ref.doc_id, "sha256": ref.sha256},
            )
        )
        return ref

    # -- run / resume ------------------------------------------------------

    def _checkpointer(self, deal_id: str) -> Any:
        """Interrupts must survive across run/resume calls: the shared Postgres
        checkpointer when persisting (also across restarts), else one in-memory
        saver per deal."""
        if self.store is not None:
            if self._pg_checkpointer is None:
                raise RuntimeError("DealRunner.start() was not awaited (no checkpointer)")
            return self._pg_checkpointer
        if deal_id not in self._checkpointers:
            self._checkpointers[deal_id] = InMemorySaver()
        return self._checkpointers[deal_id]

    def _graph_ctx(self, deal_id: str) -> NodeContext:
        budget = self._require(deal_id).budget
        llm = self.llm
        if isinstance(self.llm, LLMClient):
            llm = LLMClient(
                base_url=self.settings.litellm_base_url,
                api_key=self.settings.litellm_virtual_key,
                timeout_s=self.settings.litellm_timeout_s,
                vision_timeout_s=self.settings.litellm_vision_timeout_s,
                _acreate=self.llm._acreate,
                budget=budget,
            )
        return NodeContext(
            budget=budget,
            audit=self.audit,
            llm=llm,
            vision_enabled=bool(self.settings.llm_vision_model.strip()),
            docs=self.docs,
            anchor=self.anchor,
            redis=self.idempotency,
            approval_verifier=self.approval_verifier,
        )

    async def awaiting_decision(self, deal_id: str) -> bool:
        """True while the deal's graph is parked at a human step (approval or corrected
        document). Re-running it from the start abandons that step and, seen live, made a
        deal that was ready for approval escalate; it can only be resumed."""
        rec = self._require(deal_id)
        graph = build_graph(self._graph_ctx(deal_id), checkpointer=self._checkpointer(deal_id))
        config: RunnableConfig = {"configurable": {"thread_id": rec.thread_id}}
        snapshot = await graph.aget_state(config)
        return bool(getattr(snapshot, "interrupts", ()))

    async def run(self, deal_id: str) -> None:
        rec = self._require(deal_id)
        if rec.running:
            rec.queue.put_nowait({"type": "error", "detail": "deal already running"})
            return
        rec.running = True
        graph = build_graph(self._graph_ctx(deal_id), checkpointer=self._checkpointer(deal_id))
        config: RunnableConfig = {"configurable": {"thread_id": rec.thread_id}}
        try:
            final = await graph.ainvoke(rec.state, config)
            rec.state = DealState.model_validate(final)
            self._emit_interrupt_payload(deal_id, final)
            rec.queue.put_nowait({"type": "done", "state": rec.state.model_dump()})
        except Exception as e:
            rec.queue.put_nowait({"type": "error", "detail": type(e).__name__})
        finally:
            rec.running = False
            self._persist(deal_id)

    async def check_document_readiness(self, deal_id: str) -> DealRecord:
        """Extract uploaded docs only, without starting the full deal graph."""
        rec = self._require(deal_id)
        if rec.running:
            raise RuntimeError("deal already running")
        rec.running = True
        extract = wrap_with_hooks("extract_doc", extract_doc_node, self._graph_ctx(deal_id))
        try:
            for doc in rec.state.documents:
                existing = next(
                    (
                        item
                        for item in rec.state.extracted
                        if item.doc_id == doc.doc_id and item.sha256 == doc.sha256
                    ),
                    None,
                )
                if existing is not None:
                    continue
                extraction_state = rec.state.model_copy(update={"pending_doc": doc})
                update = await extract(extraction_state)
                if update.get("fatal_error"):
                    raise RuntimeError("document extraction failed")
                new_docs = update.get("extracted", [])
                extracted = [item for item in rec.state.extracted if item.doc_id != doc.doc_id]
                extracted.extend(new_docs)
                rec.state = rec.state.model_copy(
                    update={
                        "extracted": extracted,
                        "served_by": [*rec.state.served_by, *update.get("served_by", [])],
                        "pending_doc": None,
                    }
                )
            return rec
        finally:
            rec.running = False
            self._persist(deal_id)

    async def resume(self, deal_id: str, resume_payload: dict[str, Any]) -> None:
        from langgraph.types import Command

        rec = self._require(deal_id)
        if rec.running:
            rec.queue.put_nowait({"type": "error", "detail": "deal already running"})
            return
        if resume_payload.get("action") == "corrected_document":
            resume_payload = {
                **resume_payload,
                "documents": list(rec.state.documents),
            }
        rec.running = True
        graph = build_graph(self._graph_ctx(deal_id), checkpointer=self._checkpointer(deal_id))
        config: RunnableConfig = {"configurable": {"thread_id": rec.thread_id}}
        try:
            final = await graph.ainvoke(Command(resume=resume_payload), config)
            rec.state = DealState.model_validate(final)
            self._emit_interrupt_payload(deal_id, final)
            rec.queue.put_nowait({"type": "done", "state": rec.state.model_dump()})
        except Exception as e:
            rec.queue.put_nowait({"type": "error", "detail": type(e).__name__})
        finally:
            rec.running = False
            self._persist(deal_id)

    def _emit_interrupt_payload(self, deal_id: str, final: Any) -> None:
        """Forward the rich interrupt payload (kind, findings, fx options,
        amendment draft, ...) to the SSE queue before done."""
        interrupts = final.get("__interrupt__") if isinstance(final, dict) else None
        if not interrupts:
            return
        rec = self.deals.get(deal_id)
        if rec is None:
            return
        for intr in interrupts:
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                rec.queue.put_nowait(
                    {"type": "interrupt", "node": value.get("kind", ""), "payload": value}
                )

    def audit_trail(self, deal_id: str) -> list[dict[str, Any]]:
        tenant = self._require(deal_id).state.tenant_id
        return [
            {"kind": e.kind, "payload": e.payload, "ts": e.ts, "hash": h}
            for e, h in self.audit.trail(deal_id, tenant)
        ]

    def _require(self, deal_id: str) -> DealRecord:
        try:
            return self.deals[deal_id]
        except KeyError:
            raise KeyError(f"unknown deal {deal_id}") from None
