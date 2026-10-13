"""LLM wrapper tests with a fake transport (no live proxy needed)."""

import pytest
from app.harness.llm import (
    DegradedModelError,
    LLMClient,
    ModelOutputError,
)
from pydantic import BaseModel


class Out(BaseModel):
    answer: int


def fake_transport(responses: list[dict], calls: list[dict] | None = None):
    """Build an async transport returning queued responses in order."""

    async def create(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return responses.pop(0)

    return create


def completion(content: str, model: str = "claude-sonnet-5-5", prompt: int = 10, comp: int = 5):
    return {
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": comp},
    }


def mk(responses, calls=None) -> LLMClient:
    return LLMClient(
        base_url="http://litellm:4000",
        api_key="sk-test",
        _acreate=fake_transport(responses, calls),
    )


class TestHappyPath:
    async def test_valid_json_schema_output(self):
        client = mk([completion('{"answer": 42}')])
        r = await client.complete(
            alias="reasoner",
            system="s",
            messages=[{"role": "user", "content": "q"}],
            output_model=Out,
            node="plan",
        )
        assert r.output.answer == 42

    async def test_records_usage(self):
        client = mk([completion('{"answer": 1}', model="claude-haiku-5-5", prompt=100, comp=20)])
        r = await client.complete(
            alias="fast", system="s", messages=[], output_model=Out, node="extract_doc"
        )
        assert r.use.prompt_tokens == 100
        assert r.use.completion_tokens == 20
        assert r.use.degraded is False
        assert r.use.alias == "fast"

    async def test_schema_requested_on_first_attempt(self):
        calls: list[dict] = []
        client = mk([completion('{"answer": 1}')], calls)
        await client.complete(alias="fast", system="s", messages=[], output_model=Out)
        assert calls[0]["response_format"]["type"] == "json_schema"
        assert calls[0]["model"] == "fast"


class TestRepairRetry:
    async def test_invalid_json_repaired_once(self):
        responses = [
            completion("not json at all"),
            completion('{"answer": 7}'),
        ]
        calls: list[dict] = []
        client = mk(responses, calls)
        r = await client.complete(alias="fast", system="s", messages=[], output_model=Out)
        assert r.output.answer == 7
        assert len(calls) == 2
        # second attempt carries the repair instruction and prior bad output
        last_user = calls[1]["messages"][-1]
        assert "schema" in last_user["content"].lower()
        assert "not json at all" in [m["content"] for m in calls[1]["messages"]]

    async def test_schema_violation_then_repair(self):
        responses = [
            completion('{"answer": "not an int"}'),
            completion('{"answer": 3}'),
        ]
        client = mk(responses)
        r = await client.complete(alias="fast", system="s", messages=[], output_model=Out)
        assert r.output.answer == 3

    async def test_two_failures_raise_model_output_error(self):
        client = mk([completion("bad"), completion("still bad")])
        with pytest.raises(ModelOutputError, match="repair retry"):
            await client.complete(alias="fast", system="s", messages=[], output_model=Out)


class TestDegradedDetection:
    async def test_alt_deployment_marked_degraded(self):
        client = mk([completion('{"answer": 1}', model="claude-haiku-5-5")])
        r = await client.complete(
            alias="reasoner", system="s", messages=[], output_model=Out, allow_degraded=True
        )
        assert r.use.degraded is True

    async def test_safety_critical_refuses_degraded(self):
        client = mk([completion('{"answer": 1}', model="claude-haiku-5-5")])
        with pytest.raises(DegradedModelError, match="refuses degraded"):
            await client.complete(
                alias="reasoner",
                system="s",
                messages=[],
                output_model=Out,
                node="verify",
                allow_degraded=False,
            )

    async def test_primary_not_degraded(self):
        client = mk([completion('{"answer": 1}', model="claude-sonnet-5-5")])
        r = await client.complete(
            alias="reasoner", system="s", messages=[], output_model=Out, allow_degraded=False
        )
        assert r.use.degraded is False

    async def test_model_override_promotes_served_to_primary(self, monkeypatch):
        """A deliberate provider/model switch via env must not mark calls degraded."""
        monkeypatch.setenv("LLM_REASONER_MODEL", "gemini/gemini-3.5-pro")
        client = mk([completion('{"answer": 1}', model="gemini/gemini-3.5-pro")])
        r = await client.complete(
            alias="reasoner", system="s", messages=[], output_model=Out, allow_degraded=False
        )
        assert r.use.degraded is False

    async def test_override_served_bare_form_also_primary(self, monkeypatch):
        monkeypatch.setenv("LLM_REASONER_MODEL", "gemini/gemini-3.5-pro")
        client = mk([completion('{"answer": 1}', model="gemini-3.5-pro")])
        r = await client.complete(
            alias="reasoner", system="s", messages=[], output_model=Out, allow_degraded=False
        )
        assert r.use.degraded is False
