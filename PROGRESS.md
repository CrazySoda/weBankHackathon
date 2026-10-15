# PROGRESS

Updated: 2026-10-15 (baseline re-verified green: pytest 0 failures + 4 env-gated skips, ruff clean, mypy strict clean, calc 100%)

## Milestone status

| Milestone | Status |
|---|---|
| M0 skeleton/infra | ✅ files done; ⚠️ `docker compose up` untested until Docker Desktop WSL integration is enabled |
| M1 data layer + audit chain | ⚠️ schema and tests exist; runtime persistence and DB-backed audit are not wired |
| M2 deterministic calculators | ✅ 100% branch coverage enforced |
| M3 intake/extraction/injection + seeds | ✅ incl. 10 deals + 8 poisoned docs, deterministic PDFs |
| M4 tools/skills/prompts | ✅ registry, 9 skills, 16 prompts, loaders |
| M5 the graph | ✅ all 6 acceptance edges pass |
| M6 approval/policy/execution | ⚠️ demo Ed25519 verifier; real WebAuthn is not integrated |
| M7 API/streaming/web | ⚠️ local demo API + React console; API auth and production tenant persistence missing |
| M8 WeChat | ⚠️ client/router code exists; router is not mounted; live SOTER verification and Mini Program missing |
| M9 evals/red team | ✅ offline metrics all at target; promptfoo configs written; live-model eval + fallback drill pending |
| M10 demo hardening | ❌ not started |

## Numbers

- **Tests**: 242 passing + 4 skipped (env-gated Postgres integration): unit, graph acceptance, security, API, channels, seeds, skills
- **Gates**: ruff clean, mypy strict 0 issues (35 files), `calc/` at 100% branch coverage
- **Eval (fake extraction, live graph)**: discrepancy recall **1.0**, false alarms **0.0**,
  workflow completion **1.0**, unauthorised actions **0**, ~55 ms/deal
- Injection rules: all 8 poisoned PDFs flag with expected kind + severity (verified against generated PDFs)

## Delivered in this checkpoint (beyond previous)

- Seed suite: `backend/seed/` (deals.json, poisoned.json, deterministic PDF
  generator with byte-identical output, 30 deal PDFs + 8 poisoned PDFs) + 18
  seed tests (`tests/unit/test_seed_data.py`)
- Skills: 9 skills under `backend/skills/` (UCP 600, BD import, CN VAT refund,
  HS/GRI, sanctions, FX, cashflow, amendment drafting, explain-for-SME) each
  with SKILL.md front-matter, curated rules.yaml with real sources, tools.txt
  validated against node allowlists, 3 examples each
- Prompts: 16 per-node prompt files (role/model alias per §5, allowed tools,
  `{{skills}}` placeholder, output contract, exact untrusted-data rule) with
  content-hash versions
- Loaders: `harness/skills/loader.py` (progressive loading; rejects skills
  whose tools exceed the node allowlist) + `harness/prompts/loader.py`
- Web console: `web/` (Vite + React + TS + React Query) — deal list, findings,
  FX table, hand-rolled SVG cash-flow chart, documents with confidence bars,
  audit trail with chain verification, live SSE ticker, approval/corrected-doc
  action bars, permanent SYNTHETIC DATA badge; Dockerfile + nginx (SSE-safe)
- WeChat channel: `app/channels/wechat/` — code2Session (session_key never
  leaves server), signature-verified callbacks, Redis-cached access_token with
  single-flight refresh, deal-number-only subscription messages, SOTER
  attestation bound server-side to deal_hash; 11 tests with mocked HTTP
- Evals: `tests/eval/run_eval.py` metrics runner (recall/false-alarms/
  completion/unauthorised/latency; offline fake-extraction mode + --live flag),
  promptfoo red-team config with ASI01/ASI02/ASI07 cases + clean controls
- Fixes surfaced by integration: per-deal checkpointer (interrupts survive
  run/resume), `fatal_error`/`escalation_reason` last-wins reducers (parallel
  branch failures), corrected-upload supersedes by doc_id, verify marks
  non-reproduced findings `fixed`, late shipment reclassified non-fixable
  (needs an LC amendment, not a corrected doc), SSE forwards the full
  interrupt payload

- **Root Makefile** — `make help`: install / gates / eval / seeds / seeds-verify /
  render-config / proxy / up / down / reset-demo / web-dev / web-build / clean.
  `make seeds-verify` diffs against the committed `backend/seed/checksums.sha256`
  manifest (38 PDFs, byte-identical proven). Covers M10's one-command demo reset.
- uv everywhere (host tooling): `scripts/start_proxy.sh` renders via
  `uv run` and launches the proxy via `uvx --from litellm==1.105.0`; all docs
  use `uv run python …`; .env key-generation snippets go through uv too.

## Docs

- `README.md` — hub + quick start
- `WALKTHROUGH.md` — one deal end to end with real commands and expected output
- `REPRODUCIBILITY.md` — pins, gates, eval reproduction, byte-identical seeds
- `BUILD_PLAN.md` / `PROGRESS.md` / `DECISIONS.md` / `AGENTS.md`

- Provider/key-pool selection (DECISIONS #13): `LLM_PROVIDER` +
  `LLM_REASONER_MODEL`/`LLM_FAST_MODEL` + comma-separated
  `<PROVIDER>_API_KEYS` rendered into the LiteLLM config at startup
  (one deployment per key, router round-robins and benches failing keys);
  degraded-call detection is override-aware. 16 renderer tests.

## Session 2026-10-15 additions

- Baseline repaired (see DECISIONS 15-16); eval harness updated for signed approvals
  and grounded evidence: recall 1.0, false alarms 0.0, completion 1.0, 0 unauthorised.
- `backend/seed/rules/` curated, sourced rule pack (+ `app/rules/loader.py`): 33 rules,
  none marked verified (no primary source fetched); HS 9405 rates are flagged demo
  assumptions; conflicting filing deadline recorded as unresolved.
- `backend/seed/lifecycle/`: four synthetic end-to-end documentary-LC deals (71 PDFs,
  ground truth, timelines, per-role visibility). See its README.
- New deterministic checks `lc-late-shipment`, `ucp-late-presentation`; new
  `calc.import_tax_stack_bdt` (100% branch coverage kept).

## Remaining

1. **Live-infrastructure pass**: enable Docker Desktop WSL integration →
   `docker compose up`, LiteLLM proxy smoke test, live `extract_doc` accuracy
   run vs the ≥90% target, poisoned-doc live run for the injection-resistance
   metric, M9 fallback drill (kill primary model mid-run).
2. **M8 live**: mount and configure the WeChat routes, integrate server-side
   SOTER verification, then build Mini Program pages and validate with a test account.
3. **M10**: one-command demo reset, scripted demo deals, China model profile.
4. Implement and configure a real WebAuthn verifier for the web console.

## Post-review corrections (not yet verified)

- Approval now verifies a configured approver Ed25519 signature against a
  canonical current-state render; execution repeats the check and requires
  policy allow, no open block findings, and Redis idempotency.
- Execution act operations now go through the node-allowlisted tool registry.
- Verification rereads quoted evidence from the source PDF; ungrounded or
  inconclusive open findings fail closed to escalation.
- Runtime model calls load the versioned prompt files and selected skill
  content; prompt versions are recorded on `ModelUse`.
- Upload size is bounded while streaming and file signatures are checked;
  missing sources and unsupported image inspection fail closed.
- The web approval stub is disabled. Real WebAuthn, WeChat SOTER signature
  verification, authenticated tenant identity, Postgres-backed runner/audit/
  checkpoint wiring, image vision extraction, and live malware scanning remain
  deployment gaps. Do not treat M1/M6/M8 as production complete.
- Postgres integration tests now require an explicit dedicated test database;
  they no longer fall back to the local demo database, which they truncate.

## Last recorded quality gates (pre-review baseline; current changes are unverified)

```bash
cd backend
uv run pytest tests -q          # 242 passed, 4 skipped (env-gated)
uv run ruff check app tests     # clean
uv run mypy                     # strict, 0 issues
uv run python -m tests.eval.run_eval   # recall 1.0 / FA 0.0 / completion 1.0
```
