# ClearTrade

An agent harness that pre-flights **one cross-border export deal** for a small
business: a Shenzhen micro-exporter selling physical goods to a buyer in
Bangladesh. ClearTrade reads the trade documents, finds compliance problems,
compares FX routes, forecasts cash flow, offers trade finance — and gets a
human approval before any (sandbox) payout.

> ⚠️ **All data in this repo is synthetic.** No real customers, payments or
> customs filings. The UI carries a permanent SYNTHETIC DATA badge.

See **[BUILD_PLAN.md](BUILD_PLAN.md)** for the architecture and ground rules,
**[PROGRESS.md](PROGRESS.md)** for status, **[DECISIONS.md](DECISIONS.md)**
for choices made under ambiguity.

## Architecture in one paragraph

A LangGraph state machine (16 nodes, deterministic Python routers) wrapped in
a security harness: every node runs inside hooks (budget → node → validation →
hash-chained audit); every tool declares a node allowlist; every model call
goes through a self-hosted LiteLLM proxy (aliases `reasoner`/`fast`) with
schema-constrained output and one repair retry; every money number comes from
pure integer calculators with 100% branch coverage. Documents are parsed
locally (PyMuPDF), quarantined, screened for prompt injection (deterministic
rules + classifier), and their text is treated as untrusted data everywhere.

## Quick start

```bash
# 0. enable Docker Desktop WSL integration for this distro (WSL2), then:
cp .env.example .env          # fill in LITELLM_MASTER_KEY + ANTHROPIC_API_KEY
docker compose up --build     # postgres+pgvector, valkey, litellm, backend, web

# 1. backend tests (no services needed for unit/graph/api suites)
cd backend && uv sync && uv run pytest tests -q

# 2. evaluation over the seed suite
uv run python -m tests.eval.run_eval

# 3. web console
cd web && npm install && npm run dev     # http://localhost:5173
```

### Without Docker

The unit, graph and API suites run entirely offline (scripted models,
in-memory stores). Postgres-dependent tests (RLS, append-only audit) are
env-gated: set `TEST_DATABASE_URL` to run them.

## What a deal looks like

1. `POST /deals` → upload LC + commercial invoice (+ packing list) PDFs.
2. `POST /deals/{id}/run` → the graph extracts fields with per-field confidence,
   screens for prompt injection, checks LC consistency (UCP 600), sanctions
   (synthetic list), estimates the CN export VAT refund, ranks FX routes and
   projects 90-day cash flow.
3. Clean deals park at `human_approval`; discrepancy deals get an amendment
   draft and wait for a corrected document; injected or unfixable deals
   escalate. Everything streams over SSE.
4. Approval (ed25519-signed deal hash) → sandbox payout + audit-chain head
   anchored (MockAnchor; FISCO BCOS behind the same interface).
