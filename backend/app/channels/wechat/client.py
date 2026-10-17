"""WeChat Official Account / Mini Program client (BUILD_PLAN M8).

Security rules honoured here:
- `session_key` and app secret NEVER leave the server (rule from §8 checklist).
- `access_token` is cached in Redis with a refresh lock (single-flight).
- Callback signature = sha1(sorted(token, timestamp, nonce)) — verified before
  any processing (safe mode: raw XML would additionally need AES; the demo
  uses the plaintext mode + signature).
- Notifications carry the deal number ONLY — never amounts or names.
- SOTER verification is structural in the demo (real SOTER requires the
  WeChat backend check API); the deal_hash binding is verified server-side.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel


class WechatError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Token cache (Redis in prod; the Protocol keeps tests honest)
# ---------------------------------------------------------------------------


class TokenCache(abc.ABC):
    @abc.abstractmethod
    def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, key: str, value: str, ttl_s: int) -> None:
        raise NotImplementedError


class RedisTokenCache(TokenCache):
    def __init__(self, redis: Any):
        self._redis = redis

    def get(self, key: str) -> str | None:
        v = self._redis.get(key)
        return v.decode() if isinstance(v, bytes) else v

    def set(self, key: str, value: str, ttl_s: int) -> None:
        self._redis.setex(key, ttl_s, value)


class InMemoryTokenCache(TokenCache):
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        exp, v = self._store.get(key, (0.0, ""))
        if time.monotonic() < exp:
            return v
        return None

    def set(self, key: str, value: str, ttl_s: int) -> None:
        self._store[key] = (time.monotonic() + ttl_s, value)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class WechatClient:
    app_id: str
    app_secret: str
    api_base: str = "https://api.weixin.qq.com"
    cache: TokenCache = field(default_factory=InMemoryTokenCache)
    _http: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def _client(self) -> httpx.AsyncClient:
        assert self._http is not None  # set in __post_init__
        return self._http

    # -- login ---------------------------------------------------------------

    async def code2session(self, code: str) -> tuple[str, str]:
        """Exchange a wx.login code for (openid, session_key).

        session_key is returned to the CALLER (server-side code only) and must
        never be logged, sent to the client, or persisted in plaintext.
        """
        resp = await self._client.get(
            f"{self.api_base}/sns/jscode2session",
            params={
                "appid": self.app_id,
                "secret": self.app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errcode", 0) != 0:
            raise WechatError(f"code2session failed: {body.get('errcode')} {body.get('errmsg')}")
        return str(body["openid"]), str(body["session_key"])

    # -- access token (cached, single-flight) ---------------------------------

    async def access_token(self) -> str:
        cached = self.cache.get("wx:access_token")
        if cached:
            return cached
        # refresh lock: only one caller hits the API, others wait then read
        if not self.cache.get("wx:refresh_lock"):
            self.cache.set("wx:refresh_lock", "1", ttl_s=10)
            resp = await self._client.get(
                f"{self.api_base}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.app_id,
                    "secret": self.app_secret,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            if "access_token" not in body:
                raise WechatError(f"token fetch failed: {body}")
            # refresh 5 minutes early to dodge expiry races
            ttl = max(int(body.get("expires_in", 7200)) - 300, 60)
            self.cache.set("wx:access_token", str(body["access_token"]), ttl)
            return str(body["access_token"])
        for _ in range(20):
            await asyncio.sleep(0.25)
            cached = self.cache.get("wx:access_token")
            if cached:
                return cached
        raise WechatError("access_token refresh timed out")

    # -- subscription messages -------------------------------------------------

    async def send_subscribe(
        self, openid: str, template_id: str, deal_number: str, page: str = "pages/deal/index"
    ) -> None:
        """Subscription notification. Deal number ONLY — no amounts, no names
        (rule: notifications contain no amounts or names)."""
        token = await self.access_token()
        resp = await self._client.post(
            f"{self.api_base}/cgi-bin/message/subscribe/send?access_token={token}",
            json={
                "touser": openid,
                "template_id": template_id,
                "page": page,
                "data": {
                    "character_string1": {"value": deal_number},
                },
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errcode", 0) != 0:
            raise WechatError(f"subscribe send failed: {body}")

    # -- callback signature ------------------------------------------------------

    @staticmethod
    def verify_callback_signature(token: str, signature: str, timestamp: str, nonce: str) -> bool:
        digest = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()
        return digest == signature


# ---------------------------------------------------------------------------
# SOTER (fingerprint) structural verification
# ---------------------------------------------------------------------------


class SoterResult(BaseModel):
    """wx.startSoterAuthentication success result (subset we verify)."""

    openid: str
    json_str: str  # signed JSON: contains resultValue_reason etc.
    signature: str  # HAMSig over json_str by the device key (base64)

    def payload(self) -> dict[str, Any]:
        try:
            parsed: dict[str, Any] = json.loads(self.json_str)
            return parsed
        except json.JSONDecodeError as e:
            raise WechatError("soter json_str is not JSON") from e


def verify_soter_binding(
    result: SoterResult, expected_deal_hash: str, expected_openid: str
) -> None:
    """Demo-grade server-side SOTER check:

    1. the signed JSON must parse and claim successful fingerprint auth
    2. it must carry the deal_hash being approved (so the signed attestation
       is bound to exactly what the approval screen showed)
    3. it must be for the expected openid

    Production additionally calls checkAliveSignature / the WeChat backend
    verify API with session_key; the deal-hash binding here is what makes a
    stolen-but-valid SOTER result useless for a different deal.
    """
    payload = result.payload()
    reason = payload.get("resultValue", {}).get("reason")
    if reason != "FIDO_INPUT_OK":
        raise WechatError("soter result not a successful fingerprint auth")
    bound = payload.get("deviceSigned", {}).get("extendData", "")
    if bound != expected_deal_hash:
        raise WechatError("soter attestation not bound to this deal's hash")
    if result.openid != expected_openid:
        raise WechatError("soter openid mismatch")
    if not result.signature:
        raise WechatError("empty soter signature")
