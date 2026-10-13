# AGENTS.md

**Source of truth: [BUILD_PLAN.md](BUILD_PLAN.md).** Read it before touching
anything. Current status: [PROGRESS.md](PROGRESS.md); decisions made under
ambiguity: [DECISIONS.md](DECISIONS.md).

## Non-negotiables (BUILD_PLAN §0 — never weaken these to make a test pass)

1. Graph routing is plain Python functions in `app/graph/routers.py` — never an LLM.
2. LLMs never compute money. All tax/FX/cashflow/credit math lives in
   `app/calc/` (pure, integer minor units, 100% branch coverage enforced).
3. Untrusted text (documents, chat) goes through `extract_doc`-style
   quarantining and is wrapped in `<untrusted>` tags in prompts.
4. Tools declare node allowlists; `registry.call()` refuses and audits anything else.
5. `execute_sandbox_payout` / `anchor_hash` are only called by the deterministic
   `execute` node with a verified approval.
6. Fail closed → escalate. Never guess.
7. Audit events are written by hooks (`app/harness/hooks.py`), never node code.
8. All model calls go through the LiteLLM proxy (aliases `reasoner`/`fast`) via
   `app/harness/llm.py` — no provider SDKs in the backend.
9. Money is integers (`app/calc/money.Money`). Floats never touch amounts.
10. Synthetic data only; label it in the UI.
11. Pin everything (uv.lock hashes, image digests in docker-compose.yml).
12. No secrets in code/prompts/logs — keys live only in the LiteLLM proxy.

## Layout

```
backend/app/          FastAPI app: api/, graph/ (nodes, routers, build), harness/
                      (llm, tools, hooks, budget, policy), calc/, rules/, audit/,
                      db/, security/
backend/tests/        unit/ (no services), graph/ (compiled-graph acceptance),
                      integration/ (env-gated Postgres), api/ (httpx ASGI), eval/
backend/seed/         synthetic deals + poisoned docs + generator
backend/skills/       per-node skills (SKILL.md + rules.yaml + tools.txt + examples/)
backend/prompts/      versioned per-node prompts ({{skills}} placeholder)
web/                  React review console (Vite, TanStack Query)
miniprogram/          WeChat Mini Program (M8)
evals/promptfoo/      red-team suite (OWASP ASI01–ASI10 cases)
```

## Workflow

- Quality gates before you claim anything works:
  `cd backend && uv run pytest tests -q && uv run ruff check app tests && uv run mypy`
  `calc/` additionally enforces `--cov-fail-under=100`.
- Integration tests skip without `TEST_DATABASE_URL` / live services (Docker
  Desktop WSL integration must be enabled in this distro).
- When a requirement is unclear: add a `# DECISION:` comment, record it in
  DECISIONS.md, move on. Do not stop; do not weaken a §0 rule.
