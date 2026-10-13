# Reproducibility

Everything in this repo is deterministic by construction: pinned runtimes,
hash-locked dependencies, digest-pinned container images, and byte-identical
synthetic data. This document tells you exactly how to reproduce every number
and artefact in [PROGRESS.md](PROGRESS.md).

---

## 1. Pinned environment

| Component | Pin | Where enforced |
|---|---|---|
| Python | 3.12.x | `backend/pyproject.toml` (`requires-python`), Dockerfile base |
| Dependency manager | uv 0.9.x | `uv.lock` (generated with 0.9.26) |
| All Python deps | exact versions **with hashes** | `backend/uv.lock` (`uv sync --frozen` refuses drift) |
| Postgres + pgvector | `pgvector/pgvector@sha256:2358fcba…` (pg18) | `docker-compose.yml` |
| Cache | `valkey/valkey@sha256:081c2f5c…` (8.1-alpine) | `docker-compose.yml` |
| LLM gateway | `ghcr.io/berriai/litellm@sha256:60947db0…` (**v1.105.0**; 1.82.7/1.82.8 were malicious and are avoided) | `docker-compose.yml` |
| Langfuse (optional, profile `obs`) | `langfuse/langfuse@sha256:a343f64e…` (v3) | `docker-compose.yml` |
| LLM models | `reasoner` = claude-sonnet-5-5, `fast` = claude-haiku-5-5 (via LiteLLM aliases + fallback chain) | `litellm/config.yaml` |

Model temperature is **0.0** on every call (`app/harness/llm.py`), so even
live-model runs are as reproducible as the provider allows. All money/rating
numbers never touch a model — they come from pure integer functions in
`backend/app/calc/`.

## 2. Reproduce the test results

```bash
cd backend
uv sync --frozen          # installs exactly uv.lock, hashes verified
uv run pytest tests -q    # expect: all passed, 4 skipped (env-gated integration)
```

Expected gates (as recorded in PROGRESS.md):

```bash
uv run ruff check app tests        # clean
uv run ruff format --check app tests
uv run mypy                        # "Success: no issues found in 35 source files"
uv run pytest tests/unit/calc -q --cov=app.calc --cov-branch --cov-fail-under=100
                                   # 100% branch coverage on the money math
```

The 4 skips are Postgres/Redis integration tests (`tests/integration/`).
To run them you need a live Postgres with the RLS/init scripts applied:

```bash
docker compose up -d postgres            # or any Postgres 18 with db/init applied
export TEST_DATABASE_URL=postgresql+psycopg://cleartrade:cleartrade@localhost:5432/cleartrade
uv run pytest tests/integration -q       # RLS isolation, append-only audit, tamper detection
```

## 3. Reproduce the evaluation metrics

```bash
cd backend
uv run python -m tests.eval.run_eval
```

Offline mode (default) injects seed ground-truth extractions into the graph —
no network, no API keys — so the **graph plumbing, checks engine, FX/cashflow/
finance calculators, policy engine and routing** are what's measured:

```
discrepancy_recall         1.0      (target >= 0.90)
false_alarm_rate           0.0      (target <= 0.10)
workflow_completion        1.0      (target >= 0.95)
unauthorised_actions       0        (target == 0)
calculation_exactness      1.0
```

`--live` runs the same suite through the LiteLLM proxy (requires
`LITELLM_BASE_URL` + `LITELLM_VIRTUAL_KEY`); numbers then depend on the model
tier but the harness path is identical.

## 4. Regenerate the synthetic data (byte-identical)

The 38 seed PDFs (30 deal + 8 poisoned) are committed at
`backend/seed/deals/pdfs/` and `backend/seed/pdfs/`. Regenerating produces
**identical sha256 for every file**:

```bash
cd backend
python3 -I seed/generate_seed_docs.py          # deals
python3 -I seed/generate_seed_docs.py --poisoned
# verify: re-run and diff checksums
find seed -name '*.pdf' | sort | xargs sha256sum > /tmp/a
python3 -I seed/generate_seed_docs.py && python3 -I seed/generate_seed_docs.py --poisoned
find seed -name '*.pdf' | sort | xargs sha256sum > /tmp/b
diff /tmp/a /tmp/b                             # empty = identical
```

Determinism comes from: fixed content, fixed coordinates/fonts, empty PDF
metadata and `doc.save(..., no_new_id=True)` (PyMuPDF otherwise mints a random
PDF `/ID`). CJK lines use the built-in `china-s` font. Always run the script
with `python -I` (isolated mode) as it reads seed JSON from a data directory.

The poisoned documents are verified against the real injection rules: every
`instruction_phrase`/`hidden_text` attack string matches ≥ 1 regex in
`app/graph/nodes/injection_screen.py` (asserted by
`tests/unit/test_seed_data.py`), and running `screen_spans` over the generated
PDFs flags all 8 with the expected kind and severity.

## 5. Reproduce the graph acceptance runs

The six M5 end-to-end paths use scripted models (no network):

```bash
uv run pytest tests/graph -v
# clean deal -> approval -> execute -> receipt
# fixable discrepancy -> amendment -> corrected doc -> approval
# unfixable block -> escalate
# white-text injection -> escalate (hidden_text flagged)
# policy deny -> escalate
# approval rejected -> report (no payout)
```

Security properties (replay, modified-after-sign, wrong signer, double
submit): `uv run pytest tests/unit/security -v`.

## 6. Full stack

```bash
cp .env.example .env    # set LITELLM_MASTER_KEY, ANTHROPIC_API_KEY
docker compose up --build
curl localhost:8000/health
```

Images are digest-pinned, so the stack is bit-for-bit what was tested once
Docker Desktop WSL integration is enabled for this distro (see PROGRESS.md
"Remaining").

## 7. What is intentionally NOT reproducible

- **Live-model text** (extraction wording, explanations, amendment prose):
  same model + temperature 0 gives near-determinism, but provider-side
  updates change outputs over time. The design assumption is that model text
  is never load-bearing: numbers come from `app/calc/`, verdicts on
  `lc-consistency` findings come from re-computation, and safety-critical
  verification refuses fallback-tier models (`allow_degraded=False`).
- **Sandbox payout refs** contain a nonce; receipts differ run to run by design.
