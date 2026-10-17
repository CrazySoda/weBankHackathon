"""API tests: full HTTP flow with a scripted LLM (no live proxy).

Uses httpx.AsyncClient over ASGITransport so background run tasks and the SSE
stream share one event loop (TestClient portals cancel cross-request tasks).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from app.api.deals import DealRunner
from app.config import Settings
from app.graph.nodes.extract_doc import ExtractionOutput, FieldOut
from app.main import create_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from tests.graph.conftest import FakeLLM, make_pdf, sign_for

LC_FIELDS = [
    FieldOut(
        name="lc_amount", value="100000.00", confidence=0.99, snippet="USD 100,000.00", page=1
    ),
    FieldOut(name="currency", value="USD", confidence=0.99, page=1),
    FieldOut(name="beneficiary", value="Shenzhen Sunny Goods Co", confidence=0.98, page=1),
    FieldOut(name="applicant", value="Dhaka Trading House", confidence=0.98, page=1),
    FieldOut(name="goods_description", value="LED lamps L2", confidence=0.97, page=1),
    FieldOut(name="quantity", value="5000 pcs", confidence=0.97, page=1),
    FieldOut(name="expiry_date", value="2026-12-31", confidence=0.99, page=1),
    FieldOut(name="lc_tenor_days", value="60", confidence=0.95, page=1),
]
INV_FIELDS = [
    FieldOut(
        name="total_amount",
        value="100000.00",
        confidence=0.99,
        snippet="USD 100,000.00",
        page=1,
    ),
    FieldOut(name="currency", value="USD", confidence=0.99, page=1),
    FieldOut(name="beneficiary", value="Shenzhen Sunny Goods Co", confidence=0.98, page=1),
    FieldOut(name="goods_description", value="LED lamps L2", confidence=0.97, page=1),
    FieldOut(name="quantity", value="5000 pcs", confidence=0.97, page=1),
    FieldOut(name="shipment_date", value="2026-11-01", confidence=0.98, page=1),
]


@pytest.fixture()
def owner_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture()
def app_client(tmp_path: Path, owner_key) -> tuple[Any, DealRunner]:
    pub = owner_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    settings = Settings(
        litellm_virtual_key="sk-test",
        approval_signing_key="k",
        approval_public_keys_json=json.dumps({"owner": base64.b64encode(pub).decode()}),
    )
    app = create_app(settings)
    runner: DealRunner = app.state.runner
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
    return app, runner


async def read_stream(client: httpx.AsyncClient, deal_id: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    buffer_event = None
    async with client.stream("GET", f"/deals/{deal_id}/stream") as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                buffer_event = line[7:]
            elif line.startswith("data: ") and buffer_event:
                events.append((buffer_event, json.loads(line[6:])))
                if buffer_event in ("done", "error"):
                    break
    return events


@pytest.mark.asyncio
class TestFullFlow:
    async def test_wechat_routes_are_disabled_by_default(self, app_client):
        app, _ = app_client
        assert not any(route.path.startswith("/wechat/") for route in app.routes)

    async def test_health(self, app_client):
        app, _ = app_client
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
            assert r.json()["synthetic_data"] is True

    async def test_demo_signer_is_labelled_and_verifiable(self, app_client):
        """The demo shortcut must say what it is, and sign what the server renders."""
        from app.graph.state import SignedApproval
        from app.security.approval import approval_render, deal_hash

        app, runner = app_client
        deal_id = runner.create_deal("demo-tenant").state.deal_id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(f"/deals/{deal_id}/sign_demo")
        assert r.status_code == 200
        body = r.json()
        assert body["demo_shortcut"] is True
        assert "DEMO SHORTCUT" in body["notice"]
        assert body["synthetic_data"] is True
        approval = SignedApproval.model_validate(body["approval"])
        # the signed audit record must not claim a passkey either
        assert approval.method == "demo_key"
        assert approval.deal_hash == deal_hash(approval_render(runner.deals[deal_id].state))

    async def test_demo_signer_refused_outside_demo_env(self, tmp_path: Path):
        app = create_app(
            Settings(litellm_virtual_key="sk-test", approval_signing_key="k", env="dev")
        )
        deal_id = app.state.runner.create_deal("demo-tenant").state.deal_id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(f"/deals/{deal_id}/sign_demo")
        assert r.status_code == 403

    async def test_corrected_document_resume_through_http(self, app_client):
        app, runner = app_client
        fake = runner.llm

        def correction_hint(messages):
            content = str(messages[-1]["content"])
            if "letter_of_credit" in content:
                return ExtractionOutput(kind="letter_of_credit", fields=LC_FIELDS)
            if "commercial_invoice" in content:
                fields = list(INV_FIELDS)
                if "ORIGINAL-DISCREPANCY" in content:
                    fields[0] = fields[0].model_copy(
                        update={"value": "120000.00", "snippet": "USD 120,000.00"}
                    )
                return ExtractionOutput(kind="commercial_invoice", fields=fields)
            return ExtractionOutput(kind="unknown", fields=[])

        fake.hooks["ExtractionOutput"] = correction_hint
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
        ) as client:
            created = await client.post("/deals")
            deal_id = created.json()["deal_id"]
            for name, kind, text in [
                ("lc.pdf", "letter_of_credit", "LETTER OF CREDIT USD 100,000.00"),
                (
                    "invoice.pdf",
                    "commercial_invoice",
                    "ORIGINAL-DISCREPANCY COMMERCIAL INVOICE USD 120,000.00",
                ),
            ]:
                response = await client.post(
                    f"/deals/{deal_id}/documents",
                    files={"file": (name, make_pdf([text]), "application/pdf")},
                    data={"kind": kind},
                )
                assert response.status_code == 200

            await client.post(f"/deals/{deal_id}/run")
            first_events = await read_stream(client, deal_id)
            assert any(
                kind == "interrupt" and event["payload"].get("kind") == "await_corrected_doc"
                for kind, event in first_events
            )

            uploaded = await client.post(
                f"/deals/{deal_id}/documents",
                files={
                    "file": (
                        "corrected-invoice.pdf",
                        make_pdf(["CORRECTED COMMERCIAL INVOICE USD 100,000.00"]),
                        "application/pdf",
                    )
                },
                data={"kind": "commercial_invoice"},
            )
            assert uploaded.status_code == 200
            resumed = await client.post(
                f"/deals/{deal_id}/resume", json={"action": "corrected_document"}
            )
            assert resumed.status_code == 200
            second_events = await read_stream(client, deal_id)
            assert second_events[-1][0] == "done"
            assert not any(kind == "error" for kind, _ in second_events)

            # the pre-correction finding must be superseded, not merely outranked
            state = (await client.get(f"/deals/{deal_id}")).json()["state"]
            stale = [f for f in state["findings"] if f["rule_id"] == "lc-invoice-exceeds-lc"]
            assert all(f["status"] != "open" for f in stale), stale
            assert not [
                f for f in state["findings"] if f["severity"] == "block" and f["status"] == "open"
            ]
            assert any(
                kind == "interrupt" and event["payload"].get("kind") == "human_approval"
                for kind, event in second_events
            )

    async def test_deal_budget_is_reused_across_graph_contexts(self, app_client):
        _, runner = app_client
        record = runner.create_deal("demo-tenant")
        record.budget.tokens = 123
        first = runner._graph_ctx(record.state.deal_id)
        second = runner._graph_ctx(record.state.deal_id)
        assert first.budget is second.budget is record.budget
        assert second.budget.tokens == 123

    async def test_upload_run_stream_resume(self, app_client, tmp_path: Path, owner_key):
        app, _ = app_client
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
        ) as client:
            # 1. create deal
            r = await client.post("/deals", data={"tenant_id": "demo-tenant"})
            assert r.status_code == 200
            deal_id = r.json()["deal_id"]

            # 2. upload LC + invoice
            for name, kind, text in [
                ("lc.pdf", "letter_of_credit", "LETTER OF CREDIT USD 100,000.00"),
                ("inv.pdf", "commercial_invoice", "COMMERCIAL INVOICE USD 100,000.00"),
            ]:
                r = await client.post(
                    f"/deals/{deal_id}/documents",
                    files={"file": (name, make_pdf([text]), "application/pdf")},
                    data={"kind": kind},
                )
                assert r.status_code == 200

            # 3. rejected upload type
            r = await client.post(
                f"/deals/{deal_id}/documents",
                files={"file": ("x.exe", b"MZ...", "application/x-msdownload")},
                data={"kind": "unknown"},
            )
            assert r.status_code == 415

            # 4. run + stream to the approval interrupt
            await client.post(f"/deals/{deal_id}/run")
            events = await read_stream(client, deal_id)
            kinds = [e for e, _ in events]
            assert "interrupt" in kinds
            assert kinds[-1] == "done"

            # 5. deal state shows the approval screen data
            state = (await client.get(f"/deals/{deal_id}")).json()["state"]
            assert state["policy"]["decision"] == "allow"
            assert state["fx_options"]

            # 6. resume with approval -> execute -> receipt
            screen = next(
                p["payload"] for e, p in events if e == "interrupt" and "kind" in p["payload"]
            )
            approval = sign_for(screen, owner_key)
            await client.post(
                f"/deals/{deal_id}/resume",
                json={"action": "approve", "approval": approval},
            )
            events2 = await read_stream(client, deal_id)
            assert events2[-1][0] == "done"
            final = (await client.get(f"/deals/{deal_id}")).json()["state"]
            assert final["receipt"], (final.get("fatal_error"), final.get("escalation_reason"))
            assert final["receipt"]["payout_ref"].startswith("sandbox-")

            # 7. audit trail complete, chain verifies
            audit = (await client.get(f"/deals/{deal_id}/audit")).json()
            assert audit["chain_ok"] is True
            kinds_audit = [e["kind"] for e in audit["events"]]
            assert "deal_created" in kinds_audit
