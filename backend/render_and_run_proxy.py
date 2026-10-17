import os
import subprocess
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
repo_dir = backend_dir.parent
env_path = repo_dir / ".env"

env_vars = dict(os.environ)

if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip("'\"")

# Ensure provider and rotation keys are set
openai_keys = env_vars.get("OPENAI_API_KEYS", "")
if openai_keys:
    keys = [k.strip() for k in openai_keys.split(",") if k.strip()]
    for i, k in enumerate(keys, 1):
        env_vars[f"LLM_KEY_{i}"] = k

env_vars["LLM_PROVIDER"] = "openai"

# Render litellm config
sys.path.insert(0, str(backend_dir))
from app.harness.litellm_render import render

cfg_yaml = render(env_vars)
cfg_path = backend_dir / "litellm_config.yaml"
cfg_path.write_text(cfg_yaml, encoding="utf-8")
print(f"Rendered {cfg_path}")

cmd = [
    "uvx",
    "--from",
    "litellm[proxy]==1.63.14",
    "litellm",
    "--config",
    str(cfg_path),
    "--port",
    "4000",
]
print("Starting litellm proxy on port 4000...")
subprocess.run(cmd, env=env_vars)
