"""Create a budget-capped LiteLLM virtual key and save it to the repo .env."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_KEY = "LITELLM_VIRTUAL_KEY"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def store_key(path: Path, key: str) -> None:
    if path.exists():
        original = path.read_bytes()
        text = original.decode("utf-8-sig")
        newline = "\r\n" if b"\r\n" in original else "\n"
        mode = stat.S_IMODE(path.stat().st_mode)
    else:
        text = ""
        newline = "\n"
        mode = 0o600

    lines = text.splitlines()
    replacement = f"{ENV_KEY}={key}"
    key_line = re.compile(rf"^\s*{ENV_KEY}\s*=")
    for index, line in enumerate(lines):
        if key_line.match(line):
            lines[index] = replacement
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(replacement)

    updated = newline.join(lines) + newline
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(updated)
    try:
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def generate_key(base_url: str, master_key: str, max_budget: float, duration: str) -> str:
    payload = json.dumps(
        {
            "models": ["reasoner", "fast"],
            "max_budget": max_budget,
            "budget_duration": duration,
        }
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/key/generate",
        data=payload,
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LiteLLM returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Could not reach LiteLLM at {base_url}. Start the proxy and try again."
        ) from exc

    key = result.get("key")
    if not isinstance(key, str) or not key:
        raise RuntimeError("LiteLLM response did not contain a virtual key.")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a LiteLLM virtual key for ClearTrade and save it to .env."
    )
    parser.add_argument("--base-url", default="http://localhost:4000")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--max-budget", type=float, default=10.0, help="USD spend cap (default: 10)")
    parser.add_argument("--budget-duration", default="30d", help="LiteLLM duration (default: 30d)")
    args = parser.parse_args()

    if args.max_budget <= 0:
        parser.error("--max-budget must be greater than zero")

    env_path = args.env_file.resolve()
    values = read_env(env_path)
    master_key = values.get("LITELLM_MASTER_KEY", "")
    if not master_key:
        print(f"LITELLM_MASTER_KEY is missing in {env_path}", file=sys.stderr)
        return 2

    try:
        key = generate_key(args.base_url, master_key, args.max_budget, args.budget_duration)
        store_key(env_path, key)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Could not set up the LiteLLM virtual key: {exc}", file=sys.stderr)
        return 1

    print(f"Created a virtual key with a ${args.max_budget:g} budget for {args.budget_duration}.")
    print(f"Saved it to {env_path} as {ENV_KEY}; the key value was not printed.")
    print("Recreate the backend container so it loads the updated .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
