"""WeChat channel routes (BUILD_PLAN M8).

- GET  /wechat/callback : signature-verified verification echo + event intake
- POST /wechat/login    : code2Session server-side; returns openid only
                          (session_key never leaves the server)
- POST /wechat/approve  : SOTER-verified approval, bound server-side to the
                          deal_hash; falls back to PIN+OTP in the Mini Program

Notifications are deal-number-only (no amounts, no names).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.channels.wechat.client import (
    SoterResult,
    WechatClient,
    WechatError,
    verify_soter_binding,
)
from app.graph.state import SignedApproval, new_id
from app.security.approval import deal_hash


class WechatDeps:
    """Injected dependencies (client, runner, config) — keeps the router
    construction testable without live WeChat."""

    def __init__(self, client: WechatClient, runner: Any, callback_token: str):
        self.client = client
        self.runner = runner
        self.callback_token = callback_token


def create_wechat_router(deps: WechatDeps) -> APIRouter:
    router = APIRouter(prefix="/wechat", tags=["wechat"])

    @router.post("/login")
    async def login(body: LoginBody) -> dict[str, Any]:
        """code2Session happens HERE, server-side. Only the openid is returned;
        session_key is discarded after use in this demo flow (never sent to the
        client, never logged)."""
        try:
            openid, _session_key = await deps.client.code2session(body.code)
        except WechatError as e:
            raise HTTPException(401, str(e)) from None
        # session_key deliberately not stored: the demo doesn't decrypt data.
        return {"openid": openid}

    @router.get("/callback")
    async def callback(
        signature: Annotated[str, Query()],
        timestamp: Annotated[str, Query()],
        nonce: Annotated[str, Query()],
        echostr: Annotated[str, Query()] = "",
    ) -> dict[str, str]:
        if not WechatClient.verify_callback_signature(
            deps.callback_token, signature, timestamp, nonce
        ):
            raise HTTPException(403, "bad signature")
        # verification echo; real event XML handling lands with the account
        return {"echostr": echostr}

    @router.post("/approve")
    async def approve(body: ApproveBody) -> dict[str, Any]:
        """SOTER approval: verify the attestation binds THIS deal's hash, then
        construct the SignedApproval the graph's human_approval node expects."""
        try:
            rec = deps.runner.deals[body.deal_id]
        except KeyError:
            raise HTTPException(404, "unknown deal") from None

        # recompute what the approval screen shows and bind the hash
        state = rec.state
        render = {
            "deal_id": state.deal_id,
            "findings": [
                {"check_id": f.check_id, "rule_id": f.rule_id, "severity": f.severity}
                for f in state.findings
            ],
            "fx_options": [o.model_dump() for o in state.fx_options],
            "finance_offer": state.finance_offer.model_dump() if state.finance_offer else None,
            "amount_minor": _amount_minor(state),
        }
        h = deal_hash(render)

        try:
            verify_soter_binding(body.soter, expected_deal_hash=h, expected_openid=body.openid)
        except WechatError as e:
            raise HTTPException(403, f"soter rejected: {e}") from None

        approval = SignedApproval(
            deal_hash=h,
            approver_id=body.openid,
            method="wechat_soter",
            signature_b64=body.soter.signature,
            signed_at=_utcnow_iso(),
            nonce=new_id("nonce"),
        )
        return {"approval": approval.model_dump()}

    @router.post("/notify")
    async def notify(body: NotifyBody) -> dict[str, Any]:
        """Subscription message: deal number ONLY (no amounts or names)."""
        try:
            await deps.client.send_subscribe(
                openid=body.openid,
                template_id=body.template_id,
                deal_number=body.deal_number,
                page=body.page,
            )
        except WechatError as e:
            raise HTTPException(502, str(e)) from None
        return {"sent": True}

    return router


class LoginBody(BaseModel):
    code: str


class ApproveBody(BaseModel):
    deal_id: str
    openid: str
    soter: SoterResult


class NotifyBody(BaseModel):
    openid: str
    template_id: str
    deal_number: str
    page: str = "pages/deal/index"


def _amount_minor(state: Any) -> int | None:
    for d in state.extracted:
        if d.kind == "commercial_invoice":
            t = d.get("total_amount")
            if t is not None:
                from decimal import Decimal, InvalidOperation

                try:
                    return int((Decimal(str(t.value).replace(",", "")) * 100).quantize(Decimal(1)))
                except InvalidOperation:
                    return None
    return None


def _utcnow_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
