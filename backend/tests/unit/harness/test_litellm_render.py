"""Provider selection + comma-separated key rotation for the LiteLLM config."""

from __future__ import annotations

import pytest
from app.harness.litellm_render import load_dotenv, render, resolve, split_keys


def parse_yaml(text: str) -> dict:
    import yaml

    return yaml.safe_load(text)


class TestSplitKeys:
    def test_comma_separated(self):
        assert split_keys("k1,k2,k3") == ["k1", "k2", "k3"]

    def test_whitespace_and_empties(self):
        assert split_keys(" k1 , ,k2 ,, ") == ["k1", "k2"]

    def test_empty(self):
        assert split_keys("") == []
        assert split_keys(None) == []


class TestResolve:
    def test_provider_selection_with_defaults(self):
        provider, reasoner, fast, _keys = resolve({"LLM_PROVIDER": "google"})
        assert provider == "google"
        assert reasoner == "gemini/gemini-3.5-pro"
        assert fast == "gemini/gemini-3.5-flash"

    def test_model_overrides(self):
        _, reasoner, fast, _keys = resolve(
            {
                "LLM_PROVIDER": "anthropic",
                "LLM_REASONER_MODEL": "anthropic/claude-opus-5-5",
                "LLM_FAST_MODEL": "anthropic/claude-haiku-5-5",
            }
        )
        assert reasoner == "anthropic/claude-opus-5-5"
        assert fast == "anthropic/claude-haiku-5-5"

    def test_comma_separated_keys(self):
        _, _, _, keys = resolve({"LLM_PROVIDER": "openai", "OPENAI_API_KEYS": "a,b,c"})
        assert keys == ["a", "b", "c"]

    def test_legacy_single_key(self):
        _, _, _, keys = resolve({"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "one"})
        assert keys == ["__ENV__:ANTHROPIC_API_KEY"]

    def test_ollama_needs_no_keys(self):
        _, _, _, keys = resolve({"LLM_PROVIDER": "ollama"})
        assert keys == []

    def test_deepseek_provider(self):
        provider, reasoner, fast, keys = resolve(
            {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "ds-key"}
        )
        assert provider == "deepseek"
        assert reasoner == "deepseek/deepseek-chat"
        assert fast == "deepseek/deepseek-chat"
        assert keys == ["__ENV__:DEEPSEEK_API_KEY"]

    def test_dashscope_provider(self):
        provider, reasoner, fast, keys = resolve(
            {"LLM_PROVIDER": "dashscope", "DASHSCOPE_API_KEYS": "q1, q2"}
        )
        assert provider == "dashscope"
        assert reasoner == "dashscope/qwen-plus"
        assert fast == "dashscope/qwen-turbo"
        assert keys == ["q1", "q2"]

    def test_unknown_provider_rejected(self):
        with pytest.raises(ValueError, match="LLM_PROVIDER"):
            resolve({"LLM_PROVIDER": "palm"})


class TestRender:
    def test_one_deployment_per_key(self):
        cfg = parse_yaml(
            render(
                {
                    "LLM_PROVIDER": "anthropic",
                    "ANTHROPIC_API_KEYS": "k1,k2,k3",
                    "LITELLM_MASTER_KEY": "sk-x",
                }
            )
        )
        deployments = cfg["model_list"]
        reasoner = [d for d in deployments if d["model_name"] == "reasoner"]
        fast = [d for d in deployments if d["model_name"] == "fast"]
        assert len(reasoner) == 3 and len(fast) == 3
        # secrets never appear in the file — only env references
        assert [d["litellm_params"]["api_key"] for d in reasoner] == [
            "os.environ/LLM_KEY_1",
            "os.environ/LLM_KEY_2",
            "os.environ/LLM_KEY_3",
        ]
        assert all("k1" not in str(d) and "k2" not in str(d) for d in deployments)

    def test_ollama_has_no_api_key(self):
        cfg = parse_yaml(render({"LLM_PROVIDER": "ollama"}))
        for d in cfg["model_list"]:
            assert "api_key" not in d["litellm_params"]

    def test_rotation_settings_present(self):
        cfg = parse_yaml(
            render(
                {
                    "LLM_PROVIDER": "google",
                    "GOOGLE_API_KEYS": "a,b",
                }
            )
        )
        router = cfg["router_settings"]
        assert router["num_retries"] == 2
        assert router["cooldown_time"] == 30
        assert router["allowed_fails"] == 3
        assert {"reasoner": ["fast"]} in router["fallbacks"]

    def test_langfuse_only_when_configured(self):
        off = parse_yaml(render({"LLM_PROVIDER": "openai", "OPENAI_API_KEYS": "k"}))
        assert "callbacks" not in off.get("litellm_settings", {})
        on = parse_yaml(
            render(
                {
                    "LLM_PROVIDER": "openai",
                    "OPENAI_API_KEYS": "k",
                    "LANGFUSE_PUBLIC_KEY": "pk",
                    "LANGFUSE_SECRET_KEY": "sk",
                }
            )
        )
        assert on["litellm_settings"]["callbacks"] == ["langfuse"]

    def test_no_raw_key_ever_in_output(self):
        text = render(
            {
                "LLM_PROVIDER": "google",
                "GOOGLE_API_KEYS": "SUPER-SECRET-VALUE-1,SUPER-SECRET-VALUE-2",
            }
        )
        assert "SUPER-SECRET-VALUE-1" not in text
        assert "SUPER-SECRET-VALUE-2" not in text


class TestDotenv:
    def test_parse(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nLLM_PROVIDER=google\n\nQUOTED='x,y'\nEMPTY=\n")
        values = load_dotenv(env_file)
        assert values["LLM_PROVIDER"] == "google"
        assert values["QUOTED"] == "x,y"
        assert "EMPTY" in values

    def test_render_from_env_mapping(self):
        cfg = render({"LLM_PROVIDER": "google", "GOOGLE_API_KEYS": "g1"})
        assert "gemini/gemini-3.5-flash" in cfg
