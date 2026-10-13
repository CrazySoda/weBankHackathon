"""LiteLLM gateway wrapper (BUILD_PLAN §3.3).

All model calls go through the self-hosted LiteLLM proxy using the aliases
`reasoner` / `fast` (rule 0.8). This module is the ONLY place in the backend
that talks to an LLM endpoint.

Behaviour:
- Sends JSON-schema output format; on invalid JSON/schema: one repair retry,
  then `ModelOutputError` (nodes fail closed).
- Records deployment, tokens and cost into ModelUse entries.
- `allow_degraded=False` (safety-critical nodes): if the proxy served the call
  from a lower-tier fallback deployment, raise `DegradedModelError` → escalate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.graph.state import ModelUse

T = TypeVar("T", bound=BaseModel)

# Alias -> deployments considered "primary" for degraded-call detection.
# Matches litellm/config.yaml: only these models satisfy safety-critical calls.
PRIMARY_DEPLOYMENTS: dict[str, frozenset[str]] = {
    "reasoner": frozenset({"anthropic/claude-sonnet-5-5", "claude-sonnet-5-5"}),
    "reasoner-backup": frozenset({"anthropic/claude-sonnet-5-5", "claude-sonnet-5-5"}),
    "fast": frozenset({"anthropic/claude-haiku-5-5", "claude-haiku-5-5"}),
    "fast-backup": frozenset({"anthropic/claude-haiku-5-5", "claude-haiku-5-5"}),
    "reasoner-alt": frozenset({"anthropic/claude-haiku-5-5", "claude-haiku-5-5"}),
}

REPAIR_INSTRUCTION = (
    "Your previous reply was not valid against the required JSON schema. "
    "Return ONLY JSON that validates against the schema. No prose, no markdown fences."
)


class ModelOutputError(RuntimeError):
    """Model output failed schema validation even after one repair retry."""


class DegradedModelError(RuntimeError):
    """A safety-critical call was served by a lower-tier fallback deployment."""


class ChatCompletion(Protocol):
    """Minimal shape of an OpenAI-compatible chat completion response."""

    def model_dump(self) -> dict[str, Any]: ...


@dataclass
class CompletionResult[T: BaseModel]:
    output: T
    use: ModelUse
    raw_text: str


@dataclass
class LLMClient:
    """async client for the LiteLLM proxy.

    `_acreate` is the transport (OpenAI-compatible chat.completions.create);
    tests substitute a fake here.
    """

    base_url: str
    api_key: str
    timeout_s: float = 35.0
    _acreate: Any = None  # injected transport; defaults to AsyncOpenAI
    usage_log: list[ModelUse] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self._acreate is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                base_url=f"{self.base_url.rstrip('/')}/v1",
                api_key=self.api_key,
                timeout=self.timeout_s,
            )
            self._acreate = client.chat.completions.create

    async def complete[T: BaseModel](
        self,
        *,
        alias: str,
        system: str,
        messages: list[dict[str, str]],
        output_model: type[T],
        node: str = "",
        allow_degraded: bool = True,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult[T]:
        """One schema-constrained completion with a single repair retry."""
        schema = output_model.model_json_schema()
        convo: list[dict[str, str]] = [
            {"role": "system", "content": system},
            *messages,
        ]
        for attempt in (1, 2):
            kwargs: dict[str, Any] = {
                "model": alias,
                "messages": convo,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if attempt == 1:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_model.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                }
            resp = await self._acreate(**kwargs)
            dump = resp if isinstance(resp, dict) else resp.model_dump()
            choice = dump["choices"][0]
            raw = choice["message"]["content"] or ""
            served = dump.get("model", alias)
            usage = dump.get("usage") or {}

            parsed, err = _try_parse(raw, output_model)
            if parsed is not None:
                use = self._record_use(
                    node=node,
                    alias=alias,
                    served=served,
                    usage=usage,
                    degraded=_is_degraded(alias, served),
                )
                if use.degraded and not allow_degraded:
                    raise DegradedModelError(
                        f"{alias} served by fallback deployment {served!r}; "
                        "safety-critical node refuses degraded output"
                    )
                return CompletionResult(output=parsed, use=use, raw_text=raw)

            # repair retry: feed the bad output back with the schema
            convo = [
                *convo,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"{REPAIR_INSTRUCTION}\n\nError: {err}\n\nSchema: {json.dumps(schema)}"
                    ),
                },
            ]

        raise ModelOutputError(
            f"{output_model.__name__} invalid after repair retry; last error: {err}"
        )

    def _record_use(
        self, node: str, alias: str, served: str, usage: dict[str, Any], degraded: bool
    ) -> ModelUse:
        use = ModelUse(
            node=node,
            alias=alias,
            deployment=served,
            prompt_tokens=usage.get("prompt_tokens", 0) or 0,
            completion_tokens=usage.get("completion_tokens", 0) or 0,
            cost_minor=_cost_minor(usage),
            degraded=degraded,
        )
        self.usage_log.append(use)
        return use


def _try_parse[T: BaseModel](raw: str, model: type[T]) -> tuple[T | None, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    try:
        return model.model_validate(data), ""
    except ValidationError as e:
        return None, str(e)


def _is_degraded(alias: str, served: str) -> bool:
    primary = PRIMARY_DEPLOYMENTS.get(alias)
    if primary is None:
        return False
    return served not in primary


def _cost_minor(usage: dict[str, Any]) -> int:
    """Cost in USD minor units from LiteLLM usage extensions, if present."""
    cost = usage.get("cost") or usage.get("total_cost") or 0
    try:
        return round(float(cost) * 100)
    except (TypeError, ValueError):
        return 0
