#!/usr/bin/env bash
# Start the LiteLLM proxy outside Docker (same env contract as compose).
# Everything runs through uv — no bare python3, no manual venv:
#
#   LLM_PROVIDER=google GOOGLE_API_KEYS=k1,k2,k3 scripts/start_proxy.sh
#
# Reads .env from the repo root if present (os.environ wins). Secrets stay in
# the environment; the rendered config only contains os.environ/ references.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^\s*#' .env | grep -v '^\s*$')
  set +a
fi

: "${LLM_PROVIDER:=anthropic}"

# split the selected provider's comma-separated pool into LLM_KEY_<n>
KEYS="${ANTHROPIC_API_KEYS:-${OPENAI_API_KEYS:-${GOOGLE_API_KEYS:-}}}"
i=1
for k in ${KEYS//,/ }; do
  export "LLM_KEY_${i}=${k}"
  i=$((i + 1))
done

OUT="$(mktemp /tmp/cleartrade-litellm.XXXX.yaml)"
uv run --directory backend python -m app.harness.litellm_render > "${OUT}"
echo "rendered ${OUT} (provider=${LLM_PROVIDER}, keys=$((i - 1)))"

# pinned via uvx so the proxy version matches the compose digest pin
exec uvx --from "litellm==1.105.0" litellm --config "${OUT}" --port 4000
