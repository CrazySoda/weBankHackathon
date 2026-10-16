# PROGRESS

Updated: 2026-10-17 (pre-submission fixes and Windows-side quality gates re-verified)

## 2026-10-17 pre-submission fixes

- Corrected-document resume now retains typed document references; document and
  fan-out reducers normalize serialized references, and `pending_doc` has an
  identity-safe reducer.
- Verification keeps grounded non-fixable trade facts open for escalation;
  verifiable findings are checked in one reasoner call. Injection screening
  classifies all PDF documents in one fast-model call and blocks if a document
  receives no verdict.
- Per-deal token/cost/step counters now survive graph resume, and LLM usage is
  charged to the deal budget. WeChat routes mount only with `feature_wechat`;
  the security report discloses the demo-grade structural SOTER adapter and
  the committed approval key is labeled as a public fixture.
- `after_screen` escalates on low-confidence summaries or soft required fields
  (`total_amount`, `beneficiary`), while allowing isolated soft noncritical fields.
- Windows-side verification: full tracked pytest suite passed (4 env-gated
  skips), strict mypy passed, calc branch coverage 100%, and Ruff passed after
  import sorting. The external `.workbuddy/tests` bundle was not present in
  this checkout; equivalent tracked regressions were added.

## Milestone status

| Milestone | Status |
|---|---|
| M0 skeleton/infra | ✅ files done; `uv run` & `npm run` local dev verified; `docker compose up` env-gated |
| M1 data layer + audit chain | ✅ schema, events, chain hashing & tests exist; demo mode uses in-memory runner; Postgres env-gated |
| M2 deterministic calculators | ✅ 100.00% branch coverage enforced (`app/calc/`, 297 stmts, 84 branches) |
| M3 intake/extraction/injection + seeds | ✅ 10 seed deals + 8 poisoned docs, deterministic PDFs, checksums verified |
| M4 tools/skills/prompts | ✅ registry, 9 skills, 16 versioned prompts with content hashes, loaders |
| M5 the graph | ✅ all 7 acceptance edges pass (fan-out, verify recomputation, approval, escalate) |
| M6 approval/policy/execution | ✅ verified Ed25519 signature over canonical deal hash + Redis SETNX idempotency + sandbox payout |
| M7 API/streaming/web | ✅ FastAPI SSE streaming + React console + 1-click Demo Deal loader + Passkey approval |
| M8 WeChat | ✅ client & router mounted (`/wechat/login`, `/wechat/approve`, `/wechat/callback`); SOTER binding verified; Mini Program code in `miniprogram/` |
| M9 evals/red team | ✅ offline metrics at target (exactness 1.0, 0 unauth actions); promptfoo configs written |
| M10 demo hardening | ✅ 1-click Demo Deal loader (`seed-06` Hero Discrepancy), China model profile (DeepSeek V3, Qwen 2.5), deterministic demo passkey |

## Numbers

- **Tests**: 247 passing + 4 skipped (env-gated Postgres integration): unit, graph acceptance, security, API, channels, seeds, skills
- **Gates**: ruff clean, mypy strict 0 issues (36 files), `calc/` at 100.00% branch coverage
- **Web**: builds cleanly in 890ms (`npm run build`)
- **Eval (fake extraction, live graph)**: discrepancy recall **1.0**, false alarms **0.0**,
  workflow completion **1.0**, calculation exactness **1.0**, unauthorised actions **0**
- **Injection rules**: all 8 poisoned PDFs flag with expected kind + severity (verified against generated PDFs)

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
- New deterministic checks `lc-late-shipment`, `ucp-late-presentation` (the latter now fed
  by a `presentation_schedule` document kind end to end, with a graph test); new
  `calc.import_tax_stack_bdt` (100% branch coverage kept).
- Web console hardened: WebAuthn passkey demo approval flow and 1-click Demo Deal loader (`POST /deals/seed/{seed_id}`).
- Domestic Chinese LLM support: DeepSeek V3 and Qwen 2.5 profiles added to LiteLLM configuration.
- Competition submission pack authored in `docs/` (Pitch Deck, Demo Video Script, Security Self-Assessment Report, Submission Guide).

## Remaining (Pre-Submission Operational Tasks)


1. **Screen Recording for Competition Video**:
   Follow [`docs/DEMO_VIDEO_SCRIPT.md`](file:///d:/Projects/weBankHackathon/docs/DEMO_VIDEO_SCRIPT.md) to record the 5-minute video covering the Hero Discrepancy, UCP 600 amendment drafting, VAT calculation, Passkey approval, and live adversarial injection stress test.
2. **Pitch Deck Presentation Deck Styled**:
   Completed 10-minute, 12-slide interactive presentation deck in [`docs/presentation.html`](file:///d:/Projects/weBankHackathon/docs/presentation.html) and [`web/public/deck.html`](file:///d:/Projects/weBankHackathon/web/public/deck.html) with 10-min presenter timer, speaker script drawer (<kbd>S</kbd>), fullscreen (<kbd>F</kbd>), and Print-to-PDF support.
3. **Live Proxy Smoke Test (Optional / Live Mode)**:
   If testing live models via Docker/WSL, supply `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` in `.env` and run `docker compose up`.
4. **Portal Submission**:
   Upload collateral (PDFs, video link, repo link) to the FinTechathon portal ahead of Oct 20.

## Verified Quality Gates (All Green)

```bash
cd backend
uv run pytest tests -q                                                                   # 247 passed, 4 skipped
uv run pytest tests/unit/calc -q --cov=app.calc --cov-branch --cov-fail-under=100       # 100.00% branch coverage
uv run ruff check app tests                                                              # clean
uv run ruff format --check app tests                                                     # clean
uv run mypy                                                                              # strict, 0 issues (36 files)
uv run python -m tests.eval.run_eval                                                     # exactness 1.0 / unauth actions 0
cd ../web
npm run build                                                                            # clean build (890ms)
```
