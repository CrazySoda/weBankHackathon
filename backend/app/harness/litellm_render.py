"""Render litellm/config.yaml from environment (provider + key rotation).

Design (DECISIONS #13):
- Provider selection:  LLM_PROVIDER = anthropic | openai | google | ollama
- Model selection:     LLM_REASONER_MODEL / LLM_FAST_MODEL (LiteLLM model
                       strings, provider prefix required, e.g. gemini/gemini-3.5-flash).
                       Unset → curated defaults per provider.
- Key rotation:        <PROVIDER>_API_KEYS = "key1,key2,key3" (comma separated).
                       The renderer emits ONE deployment per key per alias, so
                       the LiteLLM router round-robins keys and benches any key
                       that 429s/503s (cooldown_time / allowed_fails) before the
                       app ever sees the error. Keys themselves stay in the
                       environment: the rendered config only ever contains
                       `api_key: os.environ/LLM_KEY_<n>` references — never the
                       secrets (BUILD_PLAN rule 0.12).

Stdlib only: this script runs inside the LiteLLM container at startup.

Usage (see docker-compose.yml / scripts/start_proxy.sh):
    python litellm_render.py > /tmp/config.yaml
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

PROVIDERS = ("anthropic", "openai", "google", "ollama", "deepseek", "dashscope")

# LiteLLM model strings (provider prefix required). Curated defaults; override
# with LLM_REASONER_MODEL / LLM_FAST_MODEL.
DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {
        "reasoner": "anthropic/claude-sonnet-5-5",
        "fast": "anthropic/claude-haiku-5-5",
    },
    "openai": {
        "reasoner": "openai/gpt-4o",
        "fast": "openai/gpt-4o-mini",
    },
    "google": {
        "reasoner": "gemini/gemini-3.5-pro",
        "fast": "gemini/gemini-3.5-flash",
    },
    "ollama": {
        "reasoner": "ollama/qwen3:32b",
        "fast": "ollama/qwen3:8b",
    },
    "deepseek": {
        "reasoner": "deepseek/deepseek-chat",
        "fast": "deepseek/deepseek-chat",
    },
    "dashscope": {
        "reasoner": "dashscope/qwen-plus",
        "fast": "dashscope/qwen-turbo",
    },
}

KEYS_ENV: dict[str, str | None] = {
    "anthropic": "ANTHROPIC_API_KEYS",
    "openai": "OPENAI_API_KEYS",
    "google": "GOOGLE_API_KEYS",
    "ollama": None,  # local runtime needs no key
    "deepseek": "DEEPSEEK_API_KEYS",
    "dashscope": "DASHSCOPE_API_KEYS",
}

LEGACY_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "ollama": "",
    "deepseek": "DEEPSEEK_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
}

MAX_TOKENS = {"reasoner": 4096, "fast": 2048}


def split_keys(raw: str | None) -> list[str]:
    """'k1, k2,,k3' -> ['k1','k2','k3'] (whitespace tolerated, empties dropped)."""
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def resolve(
    env: Mapping[str, str],
) -> tuple[str, str, str, list[str]]:
    """Resolve (provider, reasoner_model, fast_model, keys) from env mapping."""
    provider = (env.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {PROVIDERS}, got {provider!r}")
    defaults = DEFAULT_MODELS[provider]
    reasoner = env.get("LLM_REASONER_MODEL", "").strip() or defaults["reasoner"]
    fast = env.get("LLM_FAST_MODEL", "").strip() or defaults["fast"]

    keys_env_name = KEYS_ENV[provider]
    keys = split_keys(env.get(keys_env_name, "")) if keys_env_name else []
    if not keys:
        legacy = LEGACY_KEY_ENV[provider]
        if legacy and env.get(legacy, "").strip():
            keys = [f"__ENV__:{legacy}"]
    return provider, reasoner, fast, keys


def _deployment(alias: str, model: str, key_ref: str | None, index: int) -> list[str]:
    lines = [
        f"  - model_name: {alias}",
        "    litellm_params:",
        f"      model: {model}",
    ]
    if key_ref is not None:
        lines.append(f"      api_key: os.environ/{key_ref}")
    lines += [
        f"      max_tokens: {MAX_TOKENS[alias]}",
        "      timeout: 30",
    ]
    if index > 0:
        # comments make the rotation legible in the rendered file
        lines.insert(0, f"  # {alias}: key #{index + 1} (round-robined by the router)")
    return lines


def render(env: Mapping[str, str]) -> str:
    provider, reasoner, fast, keys = resolve(env)
    out: list[str] = [
        "# RENDERED FILE — do not edit by hand.",
        f"# Generated from env by app/harness/litellm_render.py (provider: {provider}).",
        "# Secrets are never written here: only os.environ/ references.",
        "",
        "model_list:",
    ]

    n = 0
    for alias, model in (("reasoner", reasoner), ("fast", fast)):
        if provider == "ollama":
            out += _deployment(alias, model, None, 0)
            n += 1
        elif keys:
            for i, key in enumerate(keys):
                if key.startswith("__ENV__:"):
                    # legacy single-key env var, referenced in place
                    out += _deployment(alias, model, key.removeprefix("__ENV__:"), i)
                else:
                    out += _deployment(alias, model, f"LLM_KEY_{i + 1}", i)
            n += len(keys)
        else:
            out += [
                f"  # WARNING: no keys configured for {provider} "
                f"({KEYS_ENV[provider] or 'n/a'} unset); "
                "deployment relies on the ambient credential.",
            ]
            out += _deployment(alias, model, None, 0)
            n += 1

    out += [
        "",
        "router_settings:",
        "  num_retries: 2",
        "  timeout: 30",
        "  allowed_fails: 3",
        "  cooldown_time: 30",
        "  fallbacks:",
        "    - reasoner: [fast]",
        "",
        "litellm_settings:",
        "  drop_params: true",
        "  request_timeout: 30",
    ]
    if env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY"):
        out.append('  callbacks: ["langfuse"]')
    out += [
        "",
        "general_settings:",
        "  master_key: os.environ/LITELLM_MASTER_KEY",
        "  database_url: os.environ/LITELLM_DB_URL",
        "",
        f"# {n} deployment(s) rendered; provider={provider}",
    ]
    return "\n".join(out) + "\n"


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE, # comments, blank lines ignored)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def main() -> None:
    # os.environ wins over .env (12-factor), .env fills the rest
    merged: dict[str, str] = {}
    for candidate in (Path(".env"), Path("../.env")):
        merged.update(load_dotenv(candidate))
    merged.update({k: v for k, v in os.environ.items() if v != ""})
    print(render(merged), end="")


if __name__ == "__main__":
    main()
