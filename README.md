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

## Tooling: [uv](https://docs.astral.sh/uv/) + one Makefile

**`make help` lists every target.** Common ones:

| Command | What it does |
|---|---|
| `make install` | backend deps from hash-locked `uv.lock` + web deps |
| `make gates` | everything CI checks: lint + mypy strict + tests + 100% calc coverage |
| `make eval` | the seed-suite metrics table (offline, deterministic) |
| `make seeds` / `make seeds-verify` | regenerate synthetic PDFs / prove byte-identical |
| `make render-config` / `make proxy` | render LiteLLM config from env / run the proxy via uvx |
| `make up` / `make down` / `make reset-demo` | docker stack lifecycle + full demo wipe |

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
# web console :5173 · api :8000/health · LiteLLM proxy :4000
make reset-demo          # anytime: wipe back to a clean demo
```

Then follow **[WALKTHROUGH.md](WALKTHROUGH.md)**.

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
miniprogram/          WeChat Mini Program (pages pending; adapter code is not mounted)
evals/promptfoo/      red-team suite (OWASP ASI01/02/07 cases + controls)
```

## Status

See [PROGRESS.md](PROGRESS.md). The local demo and offline baseline are
implemented, but current post-review changes have not been rerun through the
gates. Runtime Postgres persistence, authenticated users, real WebAuthn/SOTER,
and Mini Program pages remain incomplete.
