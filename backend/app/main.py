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
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deals import DealRunner
from app.config import Settings, get_settings
from app.security.storage import DocumentStore

SYNTHETIC_BADGE = {"synthetic_data": True}  # every response carries the demo label (rule 0.10)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="ClearTrade", version="0.1.0")
    docs = DocumentStore(Path("data/uploads"))
    runner = DealRunner(settings, docs)
    app.state.runner = runner

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "env": settings.env, **SYNTHETIC_BADGE}

    @app.post("/deals")
    async def create_deal(tenant_id: str = Form("demo-tenant")) -> dict[str, Any]:
        rec = runner.create_deal(tenant_id)
        return {"deal_id": rec.state.deal_id, **SYNTHETIC_BADGE}

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
        data = await file.read()
        if len(data) > settings.upload_max_bytes:
            raise HTTPException(413, "file too large")
        # malware scan hook point (ClamAV in prod; demo deals are synthetic)
        ref = runner.add_document(deal_id, data, file.filename, mime, kind)
        return {"doc_id": ref.doc_id, "sha256": ref.sha256, **SYNTHETIC_BADGE}

    background_tasks: set[asyncio.Task] = set()

    @app.post("/deals/{deal_id}/run")
    async def run_deal(deal_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        task = asyncio.create_task(runner.run(deal_id))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return {"started": True, "stream": f"/deals/{deal_id}/stream", **SYNTHETIC_BADGE}

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

        async def gen():
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
        task = asyncio.create_task(runner.resume(deal_id, payload.model_dump(exclude_none=True)))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return {"resumed": True, **SYNTHETIC_BADGE}

    @app.get("/deals/{deal_id}/audit")
    async def deal_audit(deal_id: str) -> dict[str, Any]:
        if deal_id not in runner.deals:
            raise HTTPException(404, "unknown deal")
        return {
            "events": runner.audit_trail(deal_id),
            "chain_ok": runner.audit.verify_chain("demo-tenant"),
            **SYNTHETIC_BADGE,
        }

    return app


class ResumeBody(BaseModel):
    action: str = "resolve"
    approval: dict[str, Any] | None = None
    note: str = ""


def _module_app() -> FastAPI | None:
    """ASGI entrypoint for `uvicorn app.main:app`. Building settings requires
    env (virtual key + signing key); tests build their own app instead."""
    import os

    if not os.environ.get("LITELLM_VIRTUAL_KEY"):
        return None
    try:
        return create_app()
    except Exception:
        return None


app = _module_app()
