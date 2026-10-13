# ClearTrade — Build Plan for the Coding Agent

You are building **ClearTrade**, an agent harness that pre-flights one cross-border export deal for a small business. The user is a Shenzhen micro-exporter selling physical goods to a buyer in Bangladesh. The harness reads the trade documents, finds compliance problems, compares FX routes, forecasts cash flow, offers trade finance, and gets a human approval before any (sandbox) payout.

This file is the source of truth. Work through the milestones in order. Each task lists its acceptance criteria; a task is done only when its tests pass.

---

## 0. Rules you must follow (non-negotiable)

1. **Workflow, not orchestrator.** Graph routing is plain Python router functions. Never let an LLM decide the next node.
2. **LLMs never compute money.** Every tax, tariff, FX, cash-flow and credit number comes from a pure Python function with unit tests. LLMs may explain numbers, never produce them.
3. **Untrusted input never reaches a tool-holding agent raw.** All files and chat text go through `intake` → `extract_doc` (no tools, schema-only output) first. Wrap any untrusted text passed later in `<untrusted>…</untrusted>`.
4. **Least privilege.** Every tool declares an allowlist of nodes. The registry refuses calls outside it and logs an audit event.
5. **No agent can act.** `execute_sandbox_payout` and `anchor_hash` are called only by the deterministic `execute` node, only with a verified signed approval and an idempotency key.
6. **Fail closed.** Missing evidence, invalid model output after one repair retry, low confidence, a policy deny or a budget breach → `escalate`. Never guess.
7. **Everything is audited.** Every node writes an `audit_event` (hash-chained) via a hook, not inside node code.
8. **All model calls go through LiteLLM** using the aliases `reasoner` and `fast`. No direct provider SDK calls anywhere.
9. **Money is integers.** Store amounts as integer minor units plus an ISO 4217 currency code. Never use floats for money.
10. **Synthetic data only.** No real customer data, no real payments, no real customs filings. Label synthetic data in the UI.
11. **Pin everything.** Use `uv.lock` with hashes. Pin LiteLLM to a reviewed, patched release (versions 1.82.7 and 1.82.8 were malicious; check advisories). Pin Docker images by digest.
12. **No secrets in code, prompts, logs or the frontend.** Provider keys live only in the LiteLLM proxy.

---

## 1. Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12, managed with `uv` |
| API | FastAPI, Pydantic v2, SSE for streaming |
| Agents | LangGraph 1.2.x, `langgraph-checkpoint-postgres` |
| LLM gateway | LiteLLM proxy (self-hosted container) |
| Models | `reasoner` = Claude Sonnet 5.5, `fast` = Claude Haiku 5.5 (via LiteLLM, with fallbacks) |
| DB | PostgreSQL 18 + pgvector, SQLAlchemy 2 + Alembic |
| Cache | Redis/Valkey |
| Parsing | Docling or PyMuPDF; `fast` vision model as fallback |
| Policy | Cedar (`cedarpy`) or OPA (Rego) |
| Chain | FISCO BCOS (local node, or a mocked anchor behind an interface) |
| Web UI | React + TypeScript (Vite), shadcn/ui, TanStack Query |
| Mobile | WeChat Mini Program (native or Taro) |
| Observability | OpenTelemetry + Langfuse (self-hosted) |
| Testing | pytest, pytest-asyncio, hypothesis, promptfoo, garak |
| Deploy | Docker Compose |

---

## 2. Repo layout

```
cleartrade/
  AGENTS.md                  # short pointer to this file + coding conventions
  BUILD_PLAN.md
  docker-compose.yml
  litellm/config.yaml
  backend/
    pyproject.toml  uv.lock
    app/
      main.py                # FastAPI app factory
      config.py              # settings from env (pydantic-settings)
      api/                   # routes: deals, documents, approvals, stream, wechat
      channels/wechat/       # WeChat adapter: login, callbacks, SOTER verify, notify
      graph/
        state.py             # DealState + sub-models
        reducers.py          # merge_by_doc_hash, merge_by_check_id
        routers.py           # pure routing functions
        build.py             # StateGraph wiring + compile
        nodes/               # one file per node
      harness/
        llm.py               # LiteLLM client wrapper (aliases, schema output, repair retry)
        tools/registry.py    # Tool dataclass, allowlist enforcement
        tools/*.py           # tool implementations
        skills/loader.py     # skill manifest + progressive loading
        prompts/loader.py    # versioned prompt loading
        hooks.py             # before/after node hooks: budget, validation, audit
        policy.py            # Cedar/OPA wrapper
        budget.py            # step/token/cost limits, kill switch
      calc/                  # pure money functions: vat_refund, landed_cost, fx, cashflow, credit
      rules/                 # rule store access (bitemporal queries)
      audit/                 # hash-chained audit log + chain anchoring interface
      db/                    # models, migrations
      security/              # auth, passkeys, idempotency, rate limit, upload scan
    prompts/<node>.md
    skills/<skill-name>/{SKILL.md, rules.yaml, tools.txt, examples/, tests/}
    seed/                    # rule pack, synthetic deals, poisoned docs
    tests/{unit, graph, security, eval}
  web/                       # React review console
  miniprogram/               # WeChat Mini Program
  evals/promptfoo/           # red-team + regression configs
```

---

## 3. Core contracts (build these first; everything depends on them)

### 3.1 DealState (`graph/state.py`)

```python
class DealState(BaseModel):
    deal_id: str
    tenant_id: str
    documents: list[DocRef]                                      # file hashes only
    extracted: Annotated[list[ExtractedDoc], merge_by_doc_hash] = []
    injection_flags: list[Flag] = []
    check_plan: CheckPlan | None = None                          # includes chosen skills
    findings: Annotated[list[Finding], merge_by_check_id] = []
    fx_options: list[FxOption] = []
    cash_projection: CashProjection | None = None
    verified: list[Finding] = []
    amendment_draft: str | None = None
    resolve_attempts: int = 0
    finance_offer: FinanceOffer | None = None
    policy: PolicyDecision | None = None
    approval: SignedApproval | None = None
    receipt: Receipt | None = None
    served_by: list[ModelUse] = []                               # which model deployment answered each call
```

Document schemas to define: `LetterOfCredit`, `CommercialInvoice`, `PackingList`, `BillOfLading` (optional). Every extracted field carries `value`, `confidence` (0–1) and `source` (page + bbox or text span).

`Finding`: `check_id`, `rule_id`, `severity` (info|warn|block), `status` (open|fixed|waived), `fixable: bool`, `evidence: list[EvidenceRef]`, `explanation`.

### 3.2 Tool contract (`harness/tools/registry.py`)

```python
@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[[BaseModel], BaseModel]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    side_effect: Literal["read", "compute", "draft", "act", "system"]
    allowed_nodes: frozenset[str]
    llm_callable: bool          # False for act/system tools
```

`registry.call(node, tool_name, args)` must: check allowlist → validate input → run → validate output → write audit event. Refusals return a structured error and log `tool_refused`.

### 3.3 LLM wrapper (`harness/llm.py`)

`complete(alias, system, messages, output_model, tools=None) -> output_model`
- Calls the LiteLLM proxy (OpenAI-compatible endpoint) with JSON-schema output.
- On invalid JSON or schema failure: one repair retry, then raise `ModelOutputError` (node fails closed).
- Records deployment served, tokens, cost into `served_by` and the trace.
- For safety-critical nodes (`verify`, anything feeding credit), pass `allow_degraded=False`: if the response came from a lower-tier fallback, raise and escalate.

### 3.4 Node hooks (`harness/hooks.py`)

Wrap every node: before (budget check, bind tool allowlist, wrap untrusted spans) → node → after (validate state update, range/currency checks, write audit event). Nodes must not write audit events themselves.

---

## 4. Milestones

### M0 — Skeleton and infra
- [ ] Repo layout above, `uv` project, pre-commit (ruff, mypy strict on `calc/`, `harness/`, `graph/`).
- [ ] `docker-compose.yml`: postgres, redis, litellm, langfuse, backend, web. Images pinned by digest.
- [ ] `litellm/config.yaml` with aliases `reasoner`, `reasoner-backup`, `reasoner-alt`, `fast`, `fast-backup`; fallbacks; retries 2; timeout 30 s; cooldown; Langfuse callbacks; master key from env. Admin UI not exposed.
- [ ] Health endpoints; OpenTelemetry wired.

**Done when:** `docker compose up` starts everything; `GET /health` is green; a test call to `fast` through LiteLLM returns and appears in Langfuse.

### M1 — Data layer and audit chain
- [ ] Tables: `trade_deal`, `document`, `rule`, `finding`, `fx_quote`, `audit_event`, plus `tenant`, `user`, `wechat_identity`.
- [ ] Postgres row-level security by `tenant_id`.
- [ ] `audit_event` append-only (no UPDATE/DELETE grants); each row stores `prev_hash` and `hash = sha256(prev_hash + canonical_json(event))`.
- [ ] `AnchorClient` interface with `MockAnchor` and `FiscoBcosAnchor`; batch-anchor the chain head.
- [ ] Rule store with bitemporal query `rules_in_force(jurisdiction, topic, as_of)`.

**Done when:** tests prove the chain detects a tampered row; RLS blocks cross-tenant reads; a rule superseded on date X is not returned for deals dated after X.

### M2 — Deterministic calculators (`calc/`)
- [ ] `export_vat_refund`, `landed_cost`, `effective_fx_cost`, `cash_projection` (90 days, what-if inputs), `finance_offer`.
- [ ] Integer minor units; explicit rounding rules; currency mismatch raises.
- [ ] Property-based tests (hypothesis) + hand-checked reference cases in `tests/unit/calc/`.

**Done when:** 100% branch coverage on `calc/`; all reference cases match exactly.

### M3 — Intake and quarantined extraction
- [ ] `POST /deals/{id}/documents`: size/type allowlist (pdf, jpg, png), malware scan hook, SHA-256, stored read-only.
- [ ] `intake` node: registers docs, emits `Send("extract_doc", …)` per document.
- [ ] `extract_doc` node: `fast` alias, **no tools**, output = document schema with per-field confidence and source.
- [ ] `injection_screen` node: rules (instruction-like phrases, hidden/white text, beneficiary change language, mismatched fonts metadata) + a `fast` classifier; `block` severity routes to `escalate`.
- [ ] Seed 10 synthetic deals (`seed/deals/`) with ground-truth JSON.

**Done when:** extraction field accuracy ≥ 90% on the seed set; all 10 seeded injection documents are flagged.

### M4 — Tools, skills and prompts
- [ ] Implement every tool in the registry table (section 6) with schemas and allowlists.
- [ ] Skill loader: read all `SKILL.md` front-matter (name, description, node) into each node's prompt; load full body + rules only for skills named in `check_plan`. Reject a skill whose `tools.txt` exceeds the node allowlist.
- [ ] Write the 9 skills (section 7), each with ≥ 3 examples and ≥ 3 test deals.
- [ ] Prompt files per node with: role, allowed tools, loaded skills, output schema, and the untrusted-data rule. Prompt version recorded on each trace.

**Done when:** registry refusal test passes for every tool/node pair not on the allowlist; skill loader tests pass.

### M5 — The graph
- [ ] Nodes: `intake`, `extract_doc`, `injection_screen`, `plan`, `compliance`, `fx`, `cashflow`, `verify`, `resolve_exception`, `await_corrected_doc`, `credit_offer`, `policy_check`, `human_approval`, `execute`, `escalate`, `report`.
- [ ] Routers in `graph/routers.py`: `fan_out_docs`, `after_screen`, `after_verify`, `after_policy`, `after_approval` — pure, unit-tested.
- [ ] Wiring as in section 5; Postgres checkpointer; `thread_id = deal_id`; `recursion_limit` = step budget.
- [ ] `verify` re-derives each finding from `read_source_doc`, never from other agents' prose.
- [ ] `resolve_exception` max 1 retry; second failure → `escalate`.
- [ ] Interrupts: `await_corrected_doc`, `human_approval`, `escalate`; resume via `Command(resume=…)`.

**Done when:** graph tests cover every edge: clean deal → approval; fixable discrepancy → resolve → clean; unfixable → escalate; injection → escalate; policy deny → escalate; approval rejected → report.

### M6 — Approval, policy and execution
- [ ] Passkeys (WebAuthn) on web; step-up required for approval.
- [ ] `deal_hash(state)` = canonical hash of exactly what the approval screen renders (findings, waivers, offer, payee, amount).
- [ ] Approval verifies signature against `deal_hash`; any state change after signing invalidates it.
- [ ] Cedar/OPA policies: amount caps, payee must match LC beneficiary, no open `block` findings, waivers need named human + reason, sanctions screen clear.
- [ ] `execute`: idempotency key in Redis, sandbox payout, anchor hash, receipt.

**Done when:** tests prove a replayed approval, a modified-after-sign deal, and a double-submit all fail safely.

### M7 — API, streaming and web console
- [ ] Endpoints: `POST /deals`, `POST /deals/{id}/documents`, `POST /deals/{id}/run`, `GET /deals/{id}`, `GET /deals/{id}/stream` (SSE), `POST /deals/{id}/resume`, `GET /deals/{id}/audit`.
- [ ] SSE events: `node_started`, `node_finished`, `finding`, `fx_options`, `cash_projection`, `interrupt`, `error`, `done`.
- [ ] Web console: deal list, document viewer with highlighted evidence, findings panel, FX panel, cash-flow chart, approval screen showing raw findings and every waiver, audit trail view, red "SYNTHETIC DATA" badge.

**Done when:** a demo deal runs end to end from the browser with live streaming.

### M8 — WeChat channel
- [ ] Adapter routes: `/wechat/login` (`code2Session` server-side only), `/wechat/callback` (signature verified, safe mode), `/wechat/approve` (SOTER result verified server-side against `deal_hash`).
- [ ] Central `access_token` cache with refresh in Redis.
- [ ] Subscription message templates: discrepancy found, corrected document received, approval needed — deal number only, no amounts or names.
- [ ] Mini Program pages: deal list, camera upload, findings stream, approval with SOTER (fallback PIN + OTP).
- [ ] Official Account chat (optional): read-only answers from the ledger via a tool-less node; chat text is never an instruction.

**Done when:** a deal can be uploaded and approved entirely from the Mini Program test account; callback signature tests pass.

### M9 — Evaluation and red team
- [ ] 50 synthetic deals with seeded errors + clean controls; 30 poisoned documents.
- [ ] `tests/eval/run_eval.py` prints the metrics table: discrepancy recall, false-alarm rate, calculation exactness, injection resistance, workflow completion, latency (time to first finding, total).
- [ ] promptfoo + garak suites in CI; build fails on any unauthorised action.
- [ ] Fallback drill: kill the primary model in LiteLLM mid-run; the run completes on the backup or escalates (never silently degrades on `verify`).

**Targets:** recall ≥ 90%, false alarms ≤ 10%, calculations exact, 0 unauthorised actions, completion ≥ 95%, first finding < 3 s, full run < 30 s.

### M10 — Demo hardening
- [ ] One-command reset of demo data.
- [ ] Scripted demo deals: clean, LC discrepancy (hero), injection attack, provider outage.
- [ ] China deployment profile: a second LiteLLM config pointing `reasoner`/`fast` at domestic models; switchable by env.

---

## 5. Graph wiring (reference)

```python
g = StateGraph(DealState)
for name, fn in NODES.items():
    g.add_node(name, wrap_with_hooks(name, fn))

g.add_edge(START, "intake")
g.add_conditional_edges("intake", fan_out_docs, ["extract_doc"])
g.add_edge("extract_doc", "injection_screen")
g.add_conditional_edges("injection_screen", after_screen)          # plan | escalate
for b in ("compliance", "fx", "cashflow"):
    g.add_edge("plan", b)
g.add_edge(["compliance", "fx", "cashflow"], "verify")
g.add_conditional_edges("verify", after_verify)                    # credit_offer | resolve_exception | escalate
g.add_edge("resolve_exception", "await_corrected_doc")
g.add_conditional_edges("await_corrected_doc", fan_out_docs, ["extract_doc"])
g.add_edge("credit_offer", "policy_check")
g.add_conditional_edges("policy_check", after_policy)              # human_approval | escalate
g.add_conditional_edges("human_approval", after_approval)          # execute | report
g.add_edge("execute", "report")
g.add_edge("escalate", "report")
g.add_edge("report", END)
```

Model per node: `extract_doc`, `fx`, `cashflow`, `injection_screen` classifier → `fast`; `plan`, `compliance`, `verify`, `resolve_exception` → `reasoner`; `credit_offer`, `policy_check`, `execute`, `report` numbers → no LLM (the `report` summary text may use `fast`).

---

## 6. Tool registry

| Tool | Class | Allowed nodes | LLM-callable |
| --- | --- | --- | --- |
| `parse_document` | read | intake, extract_doc | no (harness) |
| `lookup_rules` | read | plan, compliance | yes |
| `check_lc_documents` | compute | compliance | yes |
| `suggest_hs_code` | compute | compliance | yes (returns candidates + confidence; never auto-selects) |
| `screen_sanctions` | read | compliance | yes |
| `calc_export_vat_refund` | compute | compliance | yes |
| `calc_landed_cost` | compute | compliance, cashflow | yes |
| `get_fx_quotes` | read | fx | yes (sandbox, labelled synthetic) |
| `calc_effective_fx_cost` | compute | fx | yes |
| `project_cash_flow` | compute | cashflow | yes |
| `read_source_doc` | read | verify | yes |
| `draft_amendment` | draft | resolve_exception | yes (text only, cannot send) |
| `calc_finance_offer` | compute | credit_offer | no (harness) |
| `evaluate_policy` | compute | policy_check | no (harness) |
| `execute_sandbox_payout` | act | execute | no |
| `anchor_hash` | act | execute | no |
| `write_audit_event` | system | all, via hook | no |

---

## 7. Skills to write

`lc-ucp600-check`, `bd-import-docs`, `cn-export-vat-refund`, `hs-classification`, `sanctions-screening`, `fx-route-compare`, `cashflow-gap`, `amendment-drafting`, `explain-for-sme`.

`SKILL.md` front-matter:

```yaml
---
name: lc-ucp600-check
description: Check commercial documents for consistency with the letter of credit.
node: compliance
version: 0.1.0
---
```

Body: when to use, step-by-step method, which rule ids and tools to use, output format, common pitfalls. Rule content comes from curated `seed/rules/` with an official source link per rule; never generated at runtime.

---

## 8. Security checklist (verify before every demo build)

- [ ] OWASP Agentic Top 10 (ASI01–ASI10) mapping tests in `tests/security/` all pass.
- [ ] No tool callable outside its allowlist; no LLM-callable `act` tool exists.
- [ ] Poisoned-document suite: 0 unauthorised actions, 0 false "compliant" verdicts.
- [ ] Approval cannot be replayed or reused after a state change.
- [ ] Idempotency prevents double payout.
- [ ] Audit chain verifies end to end; head anchored.
- [ ] LiteLLM pinned, admin UI unreachable, provider keys only in the proxy, virtual key with spend cap for the backend.
- [ ] WeChat: `session_key` and app secret never leave the server; callbacks signature-verified; notifications contain no amounts or names.
- [ ] PII redacted from prompts where not needed; logs contain no secrets.
- [ ] Dependencies scanned; lockfile hashes verified in CI.

---

## 9. Working style for the agent

- Build in milestone order; do not start UI polish before M6 passes.
- Write tests with each task, not after.
- Keep nodes small: a node prepares inputs, calls `llm.complete` and/or registry tools, returns a state update. No business math inside nodes.
- When a requirement is unclear, add a `# DECISION:` comment with the choice made and list it in `DECISIONS.md`; do not stop.
- Never weaken a rule in section 0 to make a test pass. If one blocks progress, record it in `DECISIONS.md` and escalate to the team.
- After each milestone, update a short `PROGRESS.md`: what is done, what is next, known gaps.

## 10. Open decisions for the team

- Confirm the competition's preliminary deadline (20 October vs 2 November).
- Confirm primary user (Shenzhen exporter, assumed here).
- FISCO BCOS: local node or mocked anchor for the demo.
- Mini Program registration owner, or use the test account for the demo.
- Model API credits available, and which backup provider to configure.
