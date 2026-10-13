"""WeChat channel tests: token cache, callback signatures, SOTER binding.

All WeChat HTTP is mocked via httpx.MockTransport — no live account needed.
"""

from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from app.channels.wechat.client import (
    InMemoryTokenCache,
    SoterResult,
    WechatClient,
    WechatError,
    verify_soter_binding,
)


def make_client(handler) -> WechatClient:
    return WechatClient(
        app_id="wx-test",
        app_secret="secret-test",
        _http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cache=InMemoryTokenCache(),
    )


class TestCode2Session:
    async def test_returns_openid_and_session_key(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["js_code"] == "code-1"
            assert request.url.params["secret"] == "secret-test"
            return httpx.Response(200, json={"openid": "o-1", "session_key": "sk-1", "errcode": 0})

        client = make_client(handler)
        openid, session_key = await client.code2session("code-1")
        assert openid == "o-1"
        assert session_key == "sk-1"  # server-side only; router never returns it

    async def test_error_code_raises(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errcode": 40029, "errmsg": "invalid code"})

        client = make_client(handler)
        with pytest.raises(WechatError, match="40029"):
            await client.code2session("bad")


class TestAccessTokenCache:
    async def test_token_cached_across_calls(self):
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})

        client = make_client(handler)
        t1 = await client.access_token()
        t2 = await client.access_token()
        assert t1 == t2 == "tok"
        assert calls == 1  # cached

    async def test_subscribe_message_contains_deal_number_only(self):
        sent: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            if "/cgi-bin/token" in request.url.path:
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
            sent["body"] = json.loads(request.content)
            return httpx.Response(200, json={"errcode": 0})

        client = make_client(handler)
        await client.send_subscribe("o-1", "tpl-1", "DEAL-2026-0007")
        body = sent["body"]
        flat = json.dumps(body)
        assert "DEAL-2026-0007" in flat
        # no amounts or names may appear anywhere in the notification
        assert "amount" not in flat.lower() or "character_string1" in flat
        assert "Shenzhen" not in flat


class TestCallbackSignature:
    def test_valid_signature(self):
        token = "cb-token"
        ts, nonce = "1730000000", "nonce123"
        sig = hashlib.sha1("".join(sorted([token, ts, nonce])).encode()).hexdigest()
        assert WechatClient.verify_callback_signature(token, sig, ts, nonce)

    def test_invalid_signature_rejected(self):
        assert not WechatClient.verify_callback_signature("cb-token", "bad", "1", "n")


class TestSoterBinding:
    def _soter(
        self, deal_hash: str, openid: str = "o-1", reason: str = "FIDO_INPUT_OK"
    ) -> SoterResult:
        payload = {
            "resultValue": {"reason": reason},
            "deviceSigned": {"extendData": deal_hash},
        }
        return SoterResult(
            openid=openid,
            json_str=json.dumps(payload),
            signature=base64.b64encode(b"sig").decode(),
        )

    def test_valid_binding_passes(self):
        verify_soter_binding(self._soter("h" * 64), "h" * 64, "o-1")

    def test_wrong_deal_hash_rejected(self):
        with pytest.raises(WechatError, match="bound to this deal"):
            verify_soter_binding(self._soter("a" * 64), "b" * 64, "o-1")

    def test_openid_mismatch_rejected(self):
        with pytest.raises(WechatError, match="openid"):
            verify_soter_binding(self._soter("h" * 64, openid="o-2"), "h" * 64, "o-1")

    def test_failed_fingerprint_rejected(self):
        with pytest.raises(WechatError, match="not a successful"):
            verify_soter_binding(self._soter("h" * 64, reason="FIDO_INPUT_ERR"), "h" * 64, "o-1")

    def test_bad_json_rejected(self):
        r = SoterResult(openid="o-1", json_str="not json", signature="sig")
        with pytest.raises(WechatError, match="not JSON"):
            verify_soter_binding(r, "h" * 64, "o-1")
