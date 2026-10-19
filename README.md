# ClearTrade

An agent harness that pre-flights **one cross-border export deal** for a small
business: a Shenzhen micro-exporter selling physical goods to a buyer in
Bangladesh. ClearTrade reads the trade documents, finds compliance problems,
compares FX routes, forecasts cash flow, offers trade finance — and gets a
human approval before any (sandbox) payout.

> ⚠️ **All data in this repo is synthetic.** No real customers, payments or
> customs filings. The UI carries a permanent SYNTHETIC DATA badge.

## Documentation map

| Document | What it covers |
|---|---|
| **[WALKTHROUGH.md](WALKTHROUGH.md)** | Step-by-step: one deal end to end (upload → stream → approval → payout → audit), plus all three failure paths, with real commands and expected output |
| **[REPRODUCIBILITY.md](REPRODUCIBILITY.md)** | Exact pins (Python/uv/lockfile/image digests/models), how to reproduce test results, eval metrics, byte-identical seed data, and what is intentionally not reproducible |
| **[BUILD_PLAN.md](BUILD_PLAN.md)** | Architecture source of truth: non-negotiable rules (§0), milestones, graph wiring, tool registry, security checklist |
| **[PROGRESS.md](PROGRESS.md)** | Current milestone status, measured numbers, known gaps |
| **[DECISIONS.md](DECISIONS.md)** | Every decision made under ambiguity, with the why |
| **[AGENTS.md](AGENTS.md)** | Conventions and gates for anyone (human or agent) touching the code |
| **[web/README.md](web/README.md)** | The review console |

## Architecture in one paragraph

A LangGraph state machine (16 nodes, deterministic Python routers — never an
LLM) wrapped in a security harness: every node runs inside hooks (budget →
node → validation → hash-chained audit); every tool declares a node allowlist
that the registry enforces; every model call goes through a self-hosted
LiteLLM proxy (aliases `reasoner` = Sonnet 5.5, `fast` = Haiku 5.5, with
fallback chains) with schema-constrained output and one repair retry; every
money number comes from pure integer calculators with 100% branch coverage.
Documents are parsed locally (PyMuPDF), quarantined, screened for prompt
injection (deterministic rules + classifier), and their text is treated as
untrusted data everywhere. Approval is an ed25519 signature over a canonical
hash of exactly what the approval screen rendered; execution is idempotent and
sandbox-only.

**Demo approval and WeChat limits:** the committed Ed25519 signing key is a
public demo fixture, not a secret or production credential. The WeChat adapter
uses demo-grade structural SOTER checks; it does not verify biometric
attestation with WeChat's server API. Its `/wechat/*` routes are disabled by
default and mount only when `feature_wechat` is enabled. Do not treat this as
production authentication.

## Tooling: [uv](https://docs.astral.sh/uv/) + one Makefile

**`make help` lists every target.** Common ones:

| Command | What it does |
|---|---|
| `make install` | backend deps from hash-locked `uv.lock` + web deps |
| `make gates` | everything CI checks: lint + mypy strict + tests + 100% calc coverage |
| `make eval` | the seed-suite metrics table (offline, deterministic) |
| `make seeds` / `make seeds-verify` | regenerate synthetic PDFs / prove byte-identical |
| `make render-config` / `make proxy` | render LiteLLM config from env / run the proxy via uvx |
| `make up` / `make down` | production-style Docker stack lifecycle |
| `make tunnel` | start the regular stack with a temporary showcase URL |
| `make tunnel-dev` | start Vite hot reload with a temporary showcase URL |
| `make up-dev` / `make down-dev` | Docker stack with Vite hot reload for frontend edits |
| `make dev-logs` / `make logs-dev` / `make logs-web` / `make status-dev` | follow dev logs, including tunnel output |
| `make reset-demo` | full demo wipe |

uv is the only supported Python runner (never bare `python`/`pip` — the
hash-locked `uv.lock` only protects runs inside uv); the Makefile wraps it.
`backend/Dockerfile` installs uv in the image; `scripts/start_proxy.sh` uses
`uv run` / `uvx --from litellm==1.105.0`. Node/npm is used only for the web
console. Equivalent raw commands are shown in
[REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Quick start

```bash
# 0. enable Docker Desktop WSL integration for this distro (WSL2), then:
cp .env.example .env     # fill in keys (see comments; LLM_PROVIDER + *_API_KEYS)
make up                  # postgres+pgvector, valkey, litellm, backend, web
# Create the backend's spend-capped LiteLLM key and save it into .env:
make llm-key
# Then recreate backend to load the new key:
docker compose up -d --force-recreate backend
# make up-dev              # same stack, with Vite hot reload for web edits
# web console :5173 · api :8000/health · LiteLLM proxy :4000
make reset-demo          # anytime: wipe back to a clean demo
```

`make llm-key` requires the proxy to be running and uses `LITELLM_MASTER_KEY`
from `.env`. It creates a key restricted to the `reasoner` and `fast` model
aliases with a default $10/30-day spend cap, writes the key to
`LITELLM_VIRTUAL_KEY`, and never prints the secret. Adjust the cap with
`uv run --directory backend python ../scripts/generate_litellm_key.py --max-budget 25`.
For the hot-reload Compose stack, recreate the backend with
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate backend`.

Then follow **[WALKTHROUGH.md](WALKTHROUGH.md)**.

### Temporary showcase URL

To share a deployment-style URL without a domain or Cloudflare account setup,
run `make tunnel`. It prints a temporary `https://…trycloudflare.com` URL when
the tunnel is ready. For frontend hot reload, run `make tunnel-dev` instead.
`make dev-logs` follows the development stack logs, including tunnel output.
The URL changes when the tunnel restarts. Stop the app and tunnel with
`docker compose --profile tunnel down` (include both compose files when stopping
the dev stack).

Anyone with the URL can reach this demo. The demo signer and synthetic-data
workflow are not production authentication, so use this for a controlled
showcase only and keep real data and credentials out of it. See
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/).

### Without Docker (offline tests + eval)

The unit, graph, API, security, channels and seed suites run entirely offline
(scripted models, in-memory stores, committed seed PDFs):

```bash
make install   # = uv sync --frozen + npm install
make gates     # lint + mypy strict + 242 tests + 100% branch coverage on calc/
make eval      # metrics: recall 1.0 / false alarms 0.0 / completion 1.0
```

## Repository layout

```
backend/app/          FastAPI app: api/, graph/ (nodes, routers, build), harness/
                      (llm, tools registry, hooks, budget, policy), calc/
                      (pure integer money math), rules/ (checks + bitemporal
                      store), audit/ (hash chain + anchoring), db/, security/,
                      channels/wechat/
backend/tests/        unit/ · graph/ (6 end-to-end acceptance paths) ·
                      integration/ (env-gated Postgres: RLS, append-only) ·
                      api/ (httpx ASGI) · eval/ (metrics runner)
backend/seed/         10 synthetic deals + 8 poisoned docs + deterministic
                      PDF generator (byte-identical output, committed)
backend/skills/       9 skills: SKILL.md + curated rules.yaml + tools.txt +
                      examples/ (validated against node tool allowlists)
backend/prompts/      16 versioned per-node prompts
web/                  React review console (Vite + TS + React Query)
miniprogram/          WeChat Mini Program (pages pending; adapter mounts only when enabled)
evals/promptfoo/      red-team suite (OWASP ASI01/02/07 cases + controls)
```

## Status

See [PROGRESS.md](PROGRESS.md). The local demo and offline baseline are
implemented; the pre-submission fixes are checked in and the tracked offline
gates pass. Runtime Postgres persistence, authenticated users, real
WebAuthn/SOTER verification, and Mini Program pages remain incomplete.
