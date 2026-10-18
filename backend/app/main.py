"""ClearTrade API: app factory + routes (BUILD_PLAN M7).

Endpoints:
  GET    /health
  POST   /deals
  POST   /deals/{id}/documents      (multipart upload; size/type allowlist)
  POST   /deals/{id}/run
  GET    /deals/{id}
  GET    /deals/{id}/stream         (SSE: node_started/node_finished/interrupt/...)
  POST   /deals/{id}/resume
  GET    /deals/{id}/audit
  POST   /deals/{id}/copilot          (read-only deal Q&A, tool-less model call)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.copilot import CopilotLimit, CopilotRequest, CopilotService, CopilotUnverified
from app.api.deals import DealRunner
from app.audit.events import AuditEvent
from app.config import Settings, get_settings
from app.db.persistence import DealStore
from app.security.storage import DocumentStore

SYNTHETIC_BADGE = {"synthetic_data": True}  # every response carries the demo label (rule 0.10)
DEMO_SIGNER_NOTICE = (
    "DEMO SHORTCUT: signed by the server with the committed demo key, not by a human "
    "passkey. Local synthetic demo only."
)

SEED_SCENARIOS: dict[str, list[tuple[str, str]]] = {
    "clean": [
        ("letter_of_credit", "seed-01/lc.pdf"),
        ("commercial_invoice", "seed-01/inv.pdf"),
        ("packing_list", "seed-01/pl.pdf"),
    ],
    "discrepancy": [
        ("letter_of_credit", "seed-06/lc.pdf"),
        ("commercial_invoice", "seed-06/inv.pdf"),
        ("packing_list", "seed-06/pl.pdf"),
    ],
    "mismatch": [
        ("letter_of_credit", "seed-08/lc.pdf"),
        ("commercial_invoice", "seed-08/inv.pdf"),
        ("packing_list", "seed-08/pl.pdf"),
    ],
    "injection": [
        ("letter_of_credit", "seed-01/lc.pdf"),
        ("commercial_invoice", "poisoned/poison-01.pdf"),
        ("packing_list", "seed-01/pl.pdf"),
    ],
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = DocumentStore(Path("data/uploads"))
    store = DealStore(settings.sync_database_url) if settings.persist_deals else None
    runner = DealRunner(settings, docs, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await runner.start()  # opens the Postgres checkpointer when persisting
        try:
            yield
        finally:
            await runner.stop()

    app = FastAPI(title="ClearTrade", version="0.1.0", lifespan=lifespan)
    app.state.runner = runner
    copilot = CopilotService(
        max_turns=settings.copilot_max_turns_per_deal,
        max_tokens=settings.copilot_max_tokens_per_deal,
    )
    app.state.copilot = copilot

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "env": settings.env, **SYNTHETIC_BADGE}

    @app.post("/deals")
    async def create_deal() -> dict[str, Any]:
        # Single synthetic tenant in the local demo. Never trust a tenant id
        # supplied by an unauthenticated caller.
        rec = runner.create_deal(settings.default_tenant)
        return {"deal_id": rec.state.deal_id, **SYNTHETIC_BADGE}

    @app.post("/deals/demo-seed/{scenario}")
    async def demo_seed(scenario: str) -> dict[str, Any]:
        if settings.default_tenant != "demo-tenant":
            raise HTTPException(403, "Demo seeding is only available for demo-tenant")
        if scenario not in SEED_SCENARIOS:
            raise HTTPException(400, f"Unknown scenario {scenario!r}")

        rec = runner.create_deal(settings.default_tenant)
        seed_base = Path(__file__).resolve().parent.parent / "seed" / "deals" / "pdfs"

        for kind, rel_path in SEED_SCENARIOS[scenario]:
            p = seed_base / rel_path
            if not p.exists():
                raise HTTPException(500, f"Seed file missing: {rel_path}")
            data = p.read_bytes()
            runner.add_document(rec.state.deal_id, data, p.name, "application/pdf", kind)

        return {"deal_id": rec.state.deal_id, "scenario": scenario, **SYNTHETIC_BADGE}

    @app.post("/deals/{deal_id}/documents")
    async def upload_document(
        deal_id: str,
        file: Annotated[UploadFile, File()],
        kind: Annotated[str, Form()] = "unknown",
    ) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        assert file.filename is not None
        mime = file.content_type or "application/octet-stream"
        if mime not in settings.upload_allowed_types:
            raise HTTPException(415, f"file type {mime} not allowed")
        chunks: list[bytes] = []
        total = 0
        while chunk := await file.read(64 * 1024):
            total += len(chunk)
            if total > settings.upload_max_bytes:
                raise HTTPException(413, "file too large")
            chunks.append(chunk)
        data = b"".join(chunks)
        signatures = {
            "application/pdf": lambda b: b.startswith(b"%PDF-"),
            "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
            "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
        }
        signature_check = signatures.get(mime)
        if signature_check is None or not signature_check(data):
            raise HTTPException(415, "file contents do not match the declared type")
        # malware scan hook point (ClamAV in prod; demo deals are synthetic)
        ref = runner.add_document(deal_id, data, file.filename, mime, kind)
        return {"doc_id": ref.doc_id, "sha256": ref.sha256, **SYNTHETIC_BADGE}

    @app.delete("/deals/{deal_id}/documents/{doc_id}")
    async def remove_document(deal_id: str, doc_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        try:
            ref = runner.remove_document(deal_id, doc_id)
        except KeyError:
            raise HTTPException(404, "unknown document") from None
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from None
        return {"removed": True, "doc_id": ref.doc_id, **SYNTHETIC_BADGE}

    background_tasks: set[asyncio.Task[None]] = set()

    @app.post("/deals/{deal_id}/run")
    async def run_deal(deal_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        if runner.deals[deal_id].running:
            raise HTTPException(409, "deal already running")
        task = asyncio.create_task(runner.run(deal_id))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return {"started": True, "stream": f"/deals/{deal_id}/stream", **SYNTHETIC_BADGE}

    @app.post("/deals/{deal_id}/readiness")
    async def check_document_readiness(deal_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        try:
            rec = await runner.check_document_readiness(deal_id)
        except RuntimeError as error:
            if str(error) == "deal already running":
                raise HTTPException(409, "deal already running") from None
            raise HTTPException(502, "document extraction failed") from None
        return {"state": rec.state.model_dump(), "running": False, **SYNTHETIC_BADGE}

    @app.get("/deals/{deal_id}")
    async def get_deal(deal_id: str) -> dict[str, Any]:
        try:
            rec = runner.deals[deal_id]
        except KeyError:
            raise HTTPException(404, "unknown deal") from None
        return {"state": rec.state.model_dump(), "running": rec.running, **SYNTHETIC_BADGE}

    @app.get("/deals/{deal_id}/stream")
    async def stream_deal(deal_id: str) -> StreamingResponse:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        rec = runner.deals[deal_id]

        async def gen() -> AsyncIterator[str]:
            # replay any queued events, then follow live until done
            while True:
                try:
                    event = await asyncio.wait_for(rec.queue.get(), timeout=30.0)
                except TimeoutError:
                    yield f"event: ping\ndata: {json.dumps(SYNTHETIC_BADGE)}\n\n"
                    continue
                yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"
                if event["type"] in ("done", "error"):
                    break

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/deals/{deal_id}/resume")
    async def resume_deal(deal_id: str, payload: ResumeBody) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        rec = runner.deals[deal_id]
        if rec.running:
            raise HTTPException(409, "deal already running")
        if payload.action == "approve":
            open_blocks = [
                f for f in rec.state.findings if f.severity == "block" and f.status == "open"
            ]
            if open_blocks:
                raise HTTPException(
                    400, f"Cannot approve deal with {len(open_blocks)} open block finding(s)"
                )
        task = asyncio.create_task(runner.resume(deal_id, payload.model_dump(exclude_none=True)))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return {"resumed": True, **SYNTHETIC_BADGE}

    @app.post("/deals/{deal_id}/sign_demo")
    async def sign_demo(deal_id: str) -> dict[str, Any]:
        if settings.env != "demo":
            raise HTTPException(403, "demo signing unavailable in non-demo environment")
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        rec = runner.deals[deal_id]
        import base64
        from datetime import UTC, datetime

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from app.graph.state import SignedApproval, new_id
        from app.security.approval import (
            DEMO_APPROVER_ID,
            DEMO_PRIVATE_KEY_B64,
            approval_render,
            deal_hash,
            sign_approval,
        )

        priv_bytes = base64.b64decode(DEMO_PRIVATE_KEY_B64)
        priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
        render_data = approval_render(rec.state)
        h = deal_hash(render_data)
        now_str = datetime.now(UTC).isoformat()
        approval = SignedApproval(
            deal_hash=h,
            approver_id=DEMO_APPROVER_ID,
            method="demo_key",  # not a passkey: committed demo key (DECISIONS #20)
            signature_b64="",
            signed_at=now_str,
            nonce=new_id("nonce"),
        )
        sig = sign_approval(approval, priv_key)
        signed = approval.model_copy(update={"signature_b64": sig})
        # DEMO SHORTCUT (DECISIONS #20): the server signs with the committed demo key.
        # It is labelled in the response and the UI and is refused outside env=demo.
        return {
            "approval": signed.model_dump(),
            "demo_shortcut": True,
            "notice": DEMO_SIGNER_NOTICE,
            **SYNTHETIC_BADGE,
        }

    @app.post("/deals/seed/{seed_id}")
    async def load_seed_deal(seed_id: str) -> dict[str, Any]:
        """One-click demo deal loader (M10 Demo Hardening).
        Loads synthetic seed deal PDFs (e.g. seed-01 clean, seed-06 fixable discrepancy)
        directly into a new deal record ready to run."""
        seed_dir = Path(__file__).resolve().parents[1] / "seed" / "deals" / "pdfs" / seed_id
        if not seed_dir.is_dir():
            raise HTTPException(404, f"seed deal {seed_id!r} not found")
        rec = runner.create_deal(settings.default_tenant)
        for pdf_path in sorted(seed_dir.glob("*.pdf")):
            data = pdf_path.read_bytes()
            kind = "unknown"
            name_lower = pdf_path.name.lower()
            if "lc" in name_lower:
                kind = "letter_of_credit"
            elif "inv" in name_lower:
                kind = "commercial_invoice"
            elif "pl" in name_lower:
                kind = "packing_list"
            runner.add_document(rec.state.deal_id, data, pdf_path.name, "application/pdf", kind)
        return {"deal_id": rec.state.deal_id, "seed_id": seed_id, **SYNTHETIC_BADGE}

    @app.get("/deals/{deal_id}/audit")
    async def deal_audit(deal_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        return {
            "events": runner.audit_trail(deal_id),
            "chain_ok": runner.audit.verify_chain(runner.deals[deal_id].state.tenant_id),
            **SYNTHETIC_BADGE,
        }

    @app.post("/deals/{deal_id}/copilot")
    async def ask_copilot(deal_id: str, body: CopilotRequest) -> dict[str, Any]:
        try:
            rec = runner.deals[deal_id]
        except KeyError:
            raise HTTPException(404, "unknown deal") from None
        state = rec.state
        outcome = "answered"
        reply = None
        try:
            reply = await copilot.ask(runner.llm, state, body)
        except CopilotLimit:
            outcome = "limit"
        except CopilotUnverified:
            outcome = "unverified_numbers"
        except Exception as e:  # model/proxy failure: fail closed, UI falls back
            outcome = f"error:{type(e).__name__}"
        if reply is not None and reply.screened:
            outcome = "declined"
        # question text stays out of the audit log; its hash ties the event to it
        runner.audit.emit(
            AuditEvent(
                kind="copilot_asked",
                deal_id=deal_id,
                tenant_id=state.tenant_id,
                payload={
                    "node": "copilot",
                    "outcome": outcome,
                    "question_sha256": hashlib.sha256(body.question.encode("utf-8")).hexdigest(),
                    "prompt_version": reply.prompt_version if reply else "",
                    "deployment": reply.use.deployment if reply and reply.use else "",
                    "tokens": (
                        reply.use.prompt_tokens + reply.use.completion_tokens
                        if reply and reply.use
                        else 0
                    ),
                },
            )
        )
        if reply is None:
            status = 429 if outcome == "limit" else 422 if outcome == "unverified_numbers" else 503
            raise HTTPException(status, outcome)
        return {
            "answer": reply.answer,
            "card": reply.card,
            "finding_ids": reply.finding_ids,
            "follow_ups": reply.follow_ups,
            "declined": reply.screened,
            "model": reply.use.deployment if reply.use else None,
            **SYNTHETIC_BADGE,
        }

    # Demo-grade structural SOTER endpoints stay disabled unless explicitly enabled.
    if settings.feature_wechat:
        from app.channels.wechat.client import InMemoryTokenCache, WechatClient
        from app.channels.wechat.router import WechatDeps, create_wechat_router

        wx_client = WechatClient(
            app_id="wx_weBank_demo",
            app_secret="demo_secret",
            cache=InMemoryTokenCache(),
        )
        deps = WechatDeps(wx_client, runner, "demo_callback_token")
        app.include_router(create_wechat_router(deps))

    return app


class ResumeBody(BaseModel):
    action: str = "resolve"
    approval: dict[str, Any] | None = None
    note: str = ""


def _module_app() -> FastAPI | None:
    """ASGI entrypoint for `uvicorn app.main:app`. Building settings requires
    env (virtual key + signing key); tests build their own app instead."""
    import os

    try:
        from dotenv import load_dotenv

        load_dotenv()
        load_dotenv("../.env")
    except ImportError:
        pass

    if not os.environ.get("LITELLM_VIRTUAL_KEY"):
        return None
    try:
        return create_app()
    except Exception:
        return None


app = _module_app()
