# DECISIONS

Per BUILD_PLAN §9: decisions made when a requirement was unclear, each with the
choice and why. Team can veto; changes must update the code + tests.

| # | Decision | Why |
|---|----------|-----|
| 1 | Backend talks to LiteLLM proxy with the **OpenAI-compatible `AsyncOpenAI` client**, not the `litellm` python SDK | Rule 0.8 says no direct provider SDK calls; the proxy owns provider keys + fallbacks. `openai` client pointed at the proxy is the standard client for an OpenAI-compatible gateway and keeps one HTTP path. |
| 2 | LiteLLM image pinned to **v1.105.0** (`ghcr.io/berriai/litellm@sha256:60947…`) | Plan §0.11 flags 1.82.7/1.82.8 as malicious; 1.105.0 is the current release at build time (PyPI `litellm` 1.105.0). Digest resolved live from ghcr. |
| 3 | Postgres image = **`pgvector/pgvector:pg18`** (not `postgres:18`) | pgvector extension is required by the stack table; this image ships it on PG18. |
| 4 | Langfuse runs under a **compose profile `obs`** (`--profile obs`) | Langfuse v3 drags in ClickHouse/MinIO; demo stack stays lean unless observability is wanted. LiteLLM callbacks degrade gracefully without it. |
| 5 | `DealState` gains one operational field `fatal_error: str \| None` (not in plan §3.1 list) | Rule 0.6 (fail closed → escalate) needs an in-state signal routers can read, because a raised exception cannot route a conditional edge in LangGraph. Set only by hooks, checked first by every router. |
| 6 | Budget `max_steps` counts **node executions**; check is `steps >= max_steps` before each node | Makes `recursion_limit = step budget` natural; off-by-one verified by test. |
| 7 | Money comparisons/coercions use pydantic **`strict=True`** (no str/bool→int coercion) | Money is integers only (rule 0.9); silent coercion is a float-adjacent footgun. |
| 8 | Waived/fixed findings **survive check re-runs** (`merge_by_check_id`) | A human waiver must not be silently erased by a re-run; re-detection keeps the waiver (M6 policy still requires the named human + reason). |
| 9 | Zero-amount FX conversion with a positive fixed fee **raises** | A fee on nothing is a caller bug, not a −fee result. |
| 10 | DB/Redis integration tests are **env-gated** (`TEST_DATABASE_URL`, `TEST_REDIS_URL`) | Docker unavailable in this WSL distro (see PROGRESS); unit tests never require live services. |
| 11 | `Effective FX rate` scaled integer: `RATE_SCALE = 1_000_000` | Rates like 7.188 CNY/USD = 7_188_000; all integer math, no floats anywhere near money. |
| 12 | Engine for policy: **cedarpy** primary (cp312 manylinux wheel confirmed); a pure-Python deterministic fallback evaluator wraps it for tests without the native lib | Plan §1 allows Cedar or OPA; Cedar has no sidecar requirement. |
| 13 | LLM provider/model/key-pool selection via env (`LLM_PROVIDER`, `LLM_REASONER_MODEL`/`LLM_FAST_MODEL`, comma-separated `<PROVIDER>_API_KEYS`), rendered into the LiteLLM config at startup by `app/harness/litellm_render.py`; one deployment per key so the router round-robins and benches 429/503 keys; secrets stay in env (rendered file holds only `os.environ/` refs) | Matches the research-harness pattern the team asked for; keeps rule 0.8 (proxy-only) and 0.12 (no secrets in files) intact. Default provider remains anthropic. |
| 14 | Local demo deal creation is fixed to the single synthetic tenant `demo-tenant`; request-supplied tenant IDs are ignored | The demo has no authenticated tenant identity provider. Accepting caller-selected tenant IDs would imply isolation that the in-memory runner does not provide. Production tenant auth and persistence remain required. |
| 15 | `verify` upholds findings whose `check_id` is in `CALC_CHECK_IDS` (currently `vat-refund`) once their evidence is grounded in the source PDF; no model adjudicates them | Their numbers come from `calc/`; routing every info finding through the reasoner made a clean deal escalate whenever the model returned no verdict. Ungrounded calc findings still fail closed. |
| 16 | `verify` closes an `lc-consistency` finding that the deterministic battery no longer reproduces *before* the grounding check | After a corrected upload the old evidence quote legitimately disappears from the replaced PDF; requiring grounding there made fixable deals escalate. Findings that still reproduce must still be grounded. |
