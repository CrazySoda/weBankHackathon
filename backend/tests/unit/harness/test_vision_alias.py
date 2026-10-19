"""The `vision` alias: proxy config (own timeout, no text fallback) and the client's image calls."""

from __future__ import annotations

from app.harness.litellm_render import render
from app.harness.llm import LLMClient, primary_models
from pydantic import BaseModel


def parse_yaml(text: str) -> dict:
    import yaml

    return yaml.safe_load(text)


BASE = {"LLM_PROVIDER": "openai", "OPENAI_API_KEYS": "k1,k2"}


class TestVisionAliasRendering:
    def test_no_vision_alias_unless_configured(self):
        cfg = parse_yaml(render(BASE))
        assert {m["model_name"] for m in cfg["model_list"]} == {"reasoner", "fast"}

    def test_vision_alias_has_its_own_long_timeout_and_every_key(self):
        env = {**BASE, "LLM_VISION_MODEL": "openrouter/nvidia/nemotron-3.5-super-vl:free"}
        cfg = parse_yaml(render(env))
        vision = [m for m in cfg["model_list"] if m["model_name"] == "vision"]
        assert len(vision) == 2  # one per key, like the other aliases
        assert {m["litellm_params"]["timeout"] for m in vision} == {180}
        assert all(
            m["litellm_params"]["model"] == "openrouter/nvidia/nemotron-3.5-super-vl:free"
            for m in vision
        )
        text_aliases = [m for m in cfg["model_list"] if m["model_name"] != "vision"]
        assert {m["litellm_params"]["timeout"] for m in text_aliases} == {30}

    def test_a_text_model_is_never_a_fallback_for_vision(self):
        cfg = parse_yaml(render({**BASE, "LLM_VISION_MODEL": "openrouter/x/vl"}))
        for entry in cfg["router_settings"]["fallbacks"]:
            assert "vision" not in entry
            assert all("vision" not in targets for targets in entry.values())

    def test_blank_vision_model_means_none(self):
        cfg = parse_yaml(render({**BASE, "LLM_VISION_MODEL": "  "}))
        assert {m["model_name"] for m in cfg["model_list"]} == {"reasoner", "fast"}

    def test_secrets_are_still_only_references(self):
        text = render({**BASE, "LLM_VISION_MODEL": "openrouter/x/vl"})
        assert "k1" not in text and "k2" not in text
        assert "os.environ/LLM_KEY_1" in text


class Out(BaseModel):
    answer: int


def completion(content: str, model: str = "vl") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def client_with(calls: list[dict]) -> LLMClient:
    async def create(**kwargs):
        calls.append(kwargs)
        return completion('{"answer": 1}')

    return LLMClient(base_url="http://litellm:4000", api_key="sk-test", _acreate=create)


class TestVisionCalls:
    async def test_vision_alias_gets_its_own_timeout_and_accepts_image_parts(self):
        calls: list[dict] = []
        client = client_with(calls)
        client.vision_timeout_s = 77.0
        parts = [
            {"type": "text", "text": "read this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]
        await client.complete(
            alias="vision",
            system="s",
            messages=[{"role": "user", "content": parts}],
            output_model=Out,
        )
        assert calls[0]["timeout"] == 77.0
        assert calls[0]["messages"][1]["content"] == parts  # passed through untouched

    async def test_text_aliases_keep_the_client_default_timeout(self):
        calls: list[dict] = []
        await client_with(calls).complete(
            alias="fast", system="s", messages=[{"role": "user", "content": "q"}], output_model=Out
        )
        assert "timeout" not in calls[0]

    def test_vision_primary_models_follow_the_env_override(self, monkeypatch):
        monkeypatch.setenv("LLM_VISION_MODEL", "openrouter/nvidia/nemotron-3.5-super-vl:free")
        models = primary_models("vision")
        assert models is not None
        assert "openrouter/nvidia/nemotron-3.5-super-vl:free" in models  # as configured
        assert "nvidia/nemotron-3.5-super-vl:free" in models  # as the proxy may report it
