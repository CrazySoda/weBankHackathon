# PROGRESS

Updated: 2026-10-13 (third checkpoint — M0–M7 + M9 core complete)

## Milestone status

| Milestone | Status |
|---|---|
| M0 skeleton/infra | ✅ files done; ⚠️ `docker compose up` untested until Docker Desktop WSL integration is enabled |
| M1 data layer + audit chain | ✅ (Postgres integration tests env-gated) |
| M2 deterministic calculators | ✅ 100% branch coverage enforced |
| M3 intake/extraction/injection + seeds | ✅ incl. 10 deals + 8 poisoned docs, deterministic PDFs |
| M4 tools/skills/prompts | ✅ registry, 9 skills, 16 prompts, loaders |
| M5 the graph | ✅ all 6 acceptance edges pass |
| M6 approval/policy/execution | ✅ incl. replay/modified/double-submit tests |
| M7 API/streaming/web | ✅ backend + React console |
| M8 WeChat | ✅ adapter + router + tests (mocked HTTP; live account pending) |
| M9 evals/red team | ✅ offline metrics all at target; promptfoo configs written; live-model eval + fallback drill pending |
| M10 demo hardening | ❌ not started |

## Numbers

- **Tests**: 224 passing + 4 skipped (env-gated Postgres integration): unit, graph acceptance, security, API, channels, seeds, skills
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

## Docs

- `README.md` — hub + quick start
- `WALKTHROUGH.md` — one deal end to end with real commands and expected output
- `REPRODUCIBILITY.md` — pins, gates, eval reproduction, byte-identical seeds
- `BUILD_PLAN.md` / `PROGRESS.md` / `DECISIONS.md` / `AGENTS.md`

## Remaining

1. **Live-infrastructure pass**: enable Docker Desktop WSL integration →
   `docker compose up`, LiteLLM proxy smoke test, live `extract_doc` accuracy
   run vs the ≥90% target, poisoned-doc live run for the injection-resistance
   metric, M9 fallback drill (kill primary model mid-run).
2. **M8 live**: WeChat test account + Mini Program pages (backend adapter and
   routes are done and tested against mocks).
3. **M10**: one-command demo reset, scripted demo deals, China model profile.
4. Optional: real WebAuthn on the web console (currently stub-signed approval
   in the UI; backend verification is implemented and tested).

## Quality gates (all green, verified)

```bash
cd backend
uv run pytest tests -q          # 224 passed, 4 skipped (env-gated)
uv run ruff check app tests     # clean
uv run mypy                     # strict, 0 issues
uv run python -m tests.eval.run_eval   # recall 1.0 / FA 0.0 / completion 1.0
```
