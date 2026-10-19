# ClearTrade: Technical Document (first draft)

**Team:** Tech_Hoodie$ · **Topic:** E, SME Finance Copilot
**Competition:** 2026 Shenzhen International FinTech Competition (FinTechathon), International Track
**Draft date:** 2026-10-19 · **Describes:** repository `main` at commit `051e40d` (all pull requests up to #6 merged)
**Status:** first draft for review. Every statement below was checked against the code at that commit; where something is only a design intent, it says so.

> All data in the system is synthetic. No real customer data, payments or customs filings exist anywhere in it. Payments are a sandbox simulation.

---

## 0. How this document answers the submission brief

The organisers ask for technical documentation covering **system architecture, core algorithm description and security design**. A separate Security Self-Assessment Report (`SECURITY_SELF_ASSESSMENT.md`) covers permission tiers and the known-risk list.

| Brief item | Where it is answered |
|---|---|
| System architecture | §2 (components, runtime, data stores), §3 (workflow graph), §8 (web console), §9 (deployment) |
| Core algorithm description | §4 (extraction, screening, rule checks, verification, money maths, policy, approval signing, audit chain, copilot guard) |
| Security design | §5 (summary; full treatment in the self-assessment) |
| Also useful for reviewers | §6 data model, §7 API, §10 testing and evaluation, §11 changes since earlier drafts, §12 limits and roadmap |

---

## 1. Overview

### 1.1 Problem

A small exporter can lose a whole shipment to one document discrepancy under a documentary letter of credit (LC): a late shipment date, or an invoice above the LC amount. Tax and refund rules are unclear to them, and the FX route changes what the seller receives. Banks catch these problems late and by hand.

### 1.2 What ClearTrade does

ClearTrade is an agent harness that **pre-flights one cross-border export deal before any money moves**. The demo corridor is a Shenzhen seller (Shenzhen Sunny Goods Co) shipping to a buyer in Dhaka, Bangladesh (Dhaka Trading House) under a USD 100,000 documentary LC.

For one deal it:

1. reads the uploaded documents (LC, commercial invoice, packing list; PDF, PNG or JPG) and extracts fields, each with a confidence level and a verbatim quote from the source;
2. screens the documents for hidden or instruction-like text;
3. runs a deterministic UCP 600 consistency battery and an export VAT refund estimate;
4. explains each finding in plain words and drafts an amendment request for fixable problems;
5. compares three payment routes by net CNY proceeds and forecasts 90 days of cash flow;
6. computes a synthetic trade-finance offer;
7. asks a person to approve or decline, over exactly what was shown, with a signature;
8. only after a verified approval, runs a sandbox payout and anchors the audit-chain head (the anchor is a mock in this build, see §5).

A read-only **deal copilot** lets the exporter ask questions about one deal. Scanned and photographed documents are read by an optional **vision model**.

### 1.3 Design thesis

*Workflow, not orchestrator.* Language models are untrusted workers that read and write text. They never decide what happens next, never compute money, and never act. Everything that has consequences is plain, tested code, and the last word belongs to a person.

---

## 2. System architecture

### 2.1 Component view

```
                          ┌───────────────────────────────────────────────┐
   Exporter / approver    │  Web console (React 18 + TypeScript + Vite)  │
   (browser) ───────────► │  nginx, SSE-safe proxy (3600 s read timeout)  │
                          └──────────────────────┬────────────────────────┘
                                                 │ REST + Server-Sent Events
                          ┌──────────────────────▼────────────────────────┐
                          │ FastAPI backend (Python 3.12, uv, Pydantic v2) │
                          │  api/   routes, uploads, copilot, demo seeding │
                          │  graph/ LangGraph state machine (16 nodes)     │
                          │         + pure-Python routers                  │
                          │  harness/ hooks · budget · tool registry ·     │
                          │           LLM client · policy · prompts/skills │
                          │  calc/  pure integer money maths               │
                          │  rules/ UCP 600 battery + curated rule pack    │
                          │  audit/ hash chain + anchor interface          │
                          │  security/ approval signing · document store   │
                          └──────┬───────────────┬───────────────┬────────┘
                                 │               │               │
                  ┌──────────────▼───┐  ┌────────▼────────┐  ┌───▼──────────────┐
                  │ LiteLLM proxy    │  │ PostgreSQL 18   │  │ Valkey (Redis)   │
                  │ aliases:         │  │ + pgvector      │  │ payout           │
                  │ reasoner · fast  │  │ deal snapshots, │  │ idempotency keys │
                  │ · vision(opt.)   │  │ audit chain,    │  └──────────────────┘
                  │ holds provider   │  │ graph           │
                  │ keys; spend-     │  │ checkpoints     │
                  │ capped virtual   │  │ (RLS by tenant) │
                  │ key for backend  │  └─────────────────┘
                  └────────┬─────────┘
                           ▼
                  Model providers (demo: free OpenRouter models)
```

Everything runs in Docker Compose (`postgres`, `valkey`, `litellm`, `backend`, `web`; optional `langfuse` and `cloudflared` profiles). Images for Postgres, Valkey, LiteLLM and cloudflared are pinned by digest; LiteLLM is pinned to v1.105.0.

### 2.2 Layers and responsibilities

| Layer | Responsibility | Where |
|---|---|---|
| Web console | Deal list, summary, findings, documents, FX routes, cash forecast, review history, approval bar and dialog, copilot panel, document upload | `web/src` |
| API | Deal lifecycle, document upload gate, run/resume, SSE stream, audit read, copilot, demo seeding and demo signing | `backend/app/main.py`, `api/` |
| Workflow | LangGraph state machine and deterministic routers | `backend/app/graph/` |
| Harness | Wraps every node: budget, audit hooks, state invariants. Also the tool registry, LLM client, policy engine, prompt and skill loaders | `backend/app/harness/` |
| Deterministic core | All money maths, rule checks, approval hashing, audit chain | `calc/`, `rules/`, `security/`, `audit/` |
| Model gateway | The only path to any model; holds provider keys | `litellm/`, `harness/litellm_render.py`, `harness/llm.py` |
| Persistence | Deal snapshots, hash-chained audit log, graph checkpoints, content-addressed uploads | `db/`, `security/storage.py` |

### 2.3 Key architectural rules (from `BUILD_PLAN.md` §0, enforced in code)

1. Routing is plain Python (`graph/routers.py`); a model never selects the next node.
2. Models never compute money; all tax, FX, cash-flow and credit figures come from `calc/` (integer minor units, 100% branch coverage enforced).
3. Untrusted text is quarantined: documents pass through `extract_doc`, and any untrusted text passed to a model is wrapped in `<untrusted>` tags.
4. Tools declare node allowlists; `ToolRegistry.call()` refuses and audits anything else.
5. `execute_sandbox_payout` and `anchor_hash` are called only by the deterministic `execute` node, only with a verified signed approval and an idempotency key.
6. Fail closed: missing evidence, invalid model output, low confidence, policy deny or budget breach routes to `escalate`.
7. Audit events are written by hooks, not node code.
8. All model calls go through the LiteLLM proxy via `harness/llm.py`; no provider SDKs in the backend.
9. Money is integers; floats never touch amounts.
10. Synthetic data only, labelled in the UI.

### 2.4 Technology stack

| Concern | Choice |
|---|---|
| Language and packaging | Python 3.12, `uv` with a hash-locked `uv.lock` |
| API | FastAPI, Pydantic v2, Server-Sent Events |
| Workflow | LangGraph with a Postgres checkpointer (`AsyncPostgresSaver`) when persistence is on |
| Model gateway | LiteLLM proxy; OpenAI-compatible client (`AsyncOpenAI`) from the backend (DECISIONS #1) |
| Policy | Cedar (`cedarpy`) plus a deterministic fallback evaluator |
| PDF handling | PyMuPDF (text spans, rendering of scanned pages) |
| Data | PostgreSQL 18 + pgvector, Valkey; row-level security by tenant |
| Web | React 18, TypeScript, Vite, TanStack Query, `EventSource` for SSE |
| Tests | pytest, pytest-asyncio, hypothesis; promptfoo config for red-team cases |
| Models in the demo | `reasoner` and `fast` aliases on a free text model; optional `vision` alias on a free vision model. The defaults in the code (Claude Sonnet 5.5 and Haiku 5.5) are used when a provider key for them is configured. |

---

## 3. Workflow graph

### 3.1 Nodes

The graph has 16 nodes (`graph/build.py`). Every node runs inside `wrap_with_hooks`, which counts the step against the budget, writes `node_started` and `node_finished` audit events, validates the state update, and turns any exception into a `fatal_error` that routes to `escalate`.

| Node | What it does | Model use | Notes |
|---|---|---|---|
| `intake` | Registers the document references; fans out one extraction per document | none | Escalates if there are no documents |
| `extract_doc` | Reads one document into a typed schema (fields with value, confidence, source) | `fast` for text PDFs; `vision` for images and scanned PDFs | No tools. See §4.1 |
| `injection_screen` | Rules over the PDF text plus a classifier | `fast` (classifier only) | Blocks image-only documents. See §4.2 |
| `plan` | Chooses which skills apply | `reasoner` | Output filtered to a known skill list |
| `compliance` | Deterministic UCP 600 battery, sanctions screen, VAT refund estimate | `reasoner` (explanations only) | See §4.3 |
| `fx` | Ranks the three payment routes by net proceeds | none | Synthetic quote book |
| `cashflow` | 90-day projection | none | See §4.5 |
| `verify` | Re-derives each finding from the source documents | `reasoner`, `allow_degraded=False` | Uses the `read_source_doc` tool. See §4.4 |
| `resolve_exception` | Drafts an amendment request for a fixable finding | `reasoner` | Text only; at most one attempt |
| `await_corrected_doc` | Pauses (interrupt) until a corrected document is uploaded | none | Re-enters extraction |
| `credit_offer` | Computes the best synthetic finance offer | none | See §4.5 |
| `policy_check` | Evaluates the payout policy | none | Cedar plus fallback. See §4.6 |
| `human_approval` | Pauses (interrupt) for the approver's decision | none | Verifies the signature. See §4.7 |
| `execute` | Sandbox payout and audit anchor | none | Only node allowed to call the two `act` tools |
| `escalate` | Records why the deal stopped for a person | none | Reason is plain language |
| `report` | Writes the review summary | none (text assembled in code) | Includes the decline line (§11) |

### 3.2 Wiring

```
START → intake ─(after_intake)→ extract_doc* → injection_screen ─(after_screen)→ plan
                      └→ escalate                                      └→ escalate
plan → compliance ┐
plan → fx         ├→ verify ─(after_verify)→ credit_offer → policy_check ─(after_policy)→ human_approval
plan → cashflow   ┘                │                                          └→ escalate        │
                                   ├→ resolve_exception → await_corrected_doc → extract_doc*    │
                                   └→ escalate                          (after_approval)        │
                                                                   execute ← signed ────────────┤
                                                                   report  ← declined ──────────┘
execute → report ; escalate → report ; report → END
```

`extract_doc*` is the per-document fan-out (`Send`). `compliance`, `fx` and `cashflow` run in parallel and join at `verify`.

### 3.3 Routers (all pure functions, `graph/routers.py`)

| Router | Routes to | Rule |
|---|---|---|
| `after_intake` | `escalate` or fan-out | `fatal_error` set or no documents → escalate |
| `after_screen` | `escalate` or `plan` | `fatal_error`; any `block` injection flag; a document with no fields; any `low_confidence` document; `total_amount` or `beneficiary` below confidence 0.7 → escalate |
| `after_verify` | `credit_offer`, `resolve_exception` or `escalate` | An open finding that did not survive verification → escalate. No open blocks → `credit_offer`. Fixable blocks and `resolve_attempts < 1` → `resolve_exception`. Otherwise → escalate |
| `after_policy` | `human_approval` or `escalate` | No policy result or a deny → escalate |
| `after_approval` | `execute`, `report` or `escalate` | `fatal_error` → escalate; a signed approval present → `execute`; none (declined) → `report` |

Every router checks `fatal_error` first (DECISIONS #5).

### 3.4 State

`DealState` (`graph/state.py`) is the single state object. The fields added or used by recent changes: `selected_fx_route` (the approver's signed choice, `None` = best net), `declined` and `decline_note` (the approver declined), `current_extracted` (the latest upload per document kind, DECISIONS #23), `fatal_error` and `escalation_reason`. Reducers merge extractions by document hash and findings by check id, so a waiver or a fix survives a re-run (DECISIONS #8).

---

## 4. Core algorithms

### 4.1 Grounded extraction and the vision path

**Text PDFs.** PyMuPDF extracts text spans. The `fast` model returns an `ExtractionOutput` (document kind plus fields). Each field carries `value`, `confidence` in 0..1 and a `source` (page, optional box, and a `snippet`). The model-facing schema requires `snippet`, `kind` and `fields` (DECISIONS #24). **Any snippet that is not a verbatim substring of the parsed document is dropped**, so a quote shown in the console is always real text from the file. A schema failure gets one repair retry, then the node fails closed.

**Images and scanned PDFs (DECISIONS #27).** If `LLM_VISION_MODEL` is set, the page images (an uploaded image as is; a PDF with no text layer rendered by PyMuPDF at 2x, at most 3 pages) go to the `vision` alias with the same schema. The model also identifies the document type from the picture and ignores the uploaded label. The result is **always `low_confidence` with snippets dropped**, so `after_screen` parks the deal for a person. The reason: a vision model reported confidence 1.0 for corrupted values it copied verbatim, and an image has no text layer to ground a quote in. Without a vision model, an image stays an `unsupported-image` placeholder and no model sees it. Text-layer PDFs never go to vision. The alias has its own 180 s timeout and no fallback to or from a text model.

**Measured (synthetic set, free vision model):** an MT700 letter of credit, a commercial invoice and a packing list for one deal, as clean PNGs and as low-quality JPEG scans: 13/13, 15/15 and 15/15 known values on both sets (43 of 43 each), every document type identified; 31 to 327 s per deal.

### 4.2 Injection screening

`injection_screen` runs three layers on every document:

1. **Deterministic rules** (`screen_spans`): instruction-like phrases in English and Chinese (for example "ignore previous instructions", "you are now", "system prompt"), flagged `block`; beneficiary-change language, flagged `warn`; and **white or near-white text on a light page** (hidden text), flagged `block`.
2. **A `fast` classifier** over the document text (first 15,000 characters, wrapped in `<untrusted>`), one verdict per document. A document with no verdict is blocked.
3. **Fail-closed for images:** an image-only document cannot be inspected by a text screen, so it is blocked with a distinct reason, and `escalate` says "an image document cannot be screened for hidden instructions; a person must review it" rather than calling it an attack.

Warn-level flags do not stop the deal, but they are part of the signed approval render, so the approver sees them and a flag added or removed after signing invalidates the approval (DECISIONS #22).

### 4.3 Deterministic compliance checks

The UCP 600 battery (`rules/checks.py`, `run_lc_checks`) compares the LC with the invoice (and a presentation schedule when present):

| Check | What it tests |
|---|---|
| `check_amount_match` | Invoice total against the LC amount (UCP 600 Art. 18(b)) |
| `check_expiry_after_shipment` | Shipment date against LC expiry |
| `check_latest_shipment` | Shipment date against the LC latest shipment date (unfixable by a corrected document; needs an LC amendment) |
| `check_presentation_period` | Presentation within 21 days of shipment (UCP 600 Art. 14(c)) |
| `check_goods_description` | Goods description consistency |
| `check_quantity` | Quantity consistency |
| `check_beneficiary` | LC beneficiary against the invoice payee (a mismatch is a block) |

Further checks in the same node: a sanctions screen against a **synthetic** list, and the export VAT refund estimate from `calc/vat_refund.py`. A curated rule pack of 33 sourced rules lives in `backend/seed/rules/`; none is marked verified against a primary source (see §12). The `reasoner` writes only the plain-language explanation of a finding that the deterministic code already produced (what it means, what to do next, the rule behind it).

### 4.4 Verification

`verify` never trusts another node's prose. For each finding it re-runs the deterministic battery against the source documents. Findings the battery no longer reproduces are closed (this handles a corrected upload). Calculator findings (`vat-refund`) are upheld once their evidence is grounded in the PDF (DECISIONS #15). The remaining findings are judged in **one `reasoner` call with `allow_degraded=False`**: if the gateway answers from a lower-tier fallback deployment, the call raises and the deal escalates. The node reads the source through the registered `read_source_doc` tool (allowlisted to `verify` only).

### 4.5 Money maths (`backend/app/calc`, no floats, 100% branch coverage)

All amounts are `Money(minor: int, currency: str)`. Rounding is half-up and stated. A currency mismatch raises.

| Calculator | Formula |
|---|---|
| Export VAT refund (`vat_refund.py`) | `refund = min( round_half_up(refund_base × refund_rate_bp / 10 000), input_vat )`. The cap at the input VAT is reported (`capped_by_input_vat`), because over-rebating is a fraud vector. |
| FX route (`fx.py`) | `converted = round_half_up(amount × mid_rate_scaled / 1 000 000)`; `net = converted − spread(converted) − fixed_fee`; effective rate = `net` per 1 sell unit, scaled by 1 000 000. Three synthetic routes ranked by `net`: `wire-usd-hk` (mid 7.188, spread 35 bp, fee CNY 150), `forward-lock` (7.170, 20 bp, CNY 100), `cny-direct` (7.150, 10 bp, CNY 50). |
| Finance offer (`finance.py`) | `advance = face × advance_rate_bp / 10 000`; `interest = advance × annual_rate_bp × days / (10 000 × 360)`; `net = advance − interest − flat_fee`. Cost is restated as an annualised rate on net proceeds so providers compare. The node evaluates three synthetic provider terms and keeps the offer with the highest net proceeds. |
| Cash projection (`cashflow.py`) | A list of dated events folded into a daily balance over 90 days; reports opening balance, minimum balance and day, days below zero. The demo model uses a 30% production deposit on day 0 and the LC receipt at maturity. |
| Landed cost (`landed_cost.py`, `import_tax_stack_bdt`) | Customs duty, advance income tax and fees on CIF for Bangladesh. **Present and unit-tested in the library, but not called by any graph node** (see §12). |

### 4.6 Policy

`policy_check` evaluates five rules for the payout: the amount is positive and within the cap (demo cap USD 1,000,000); the payee equals the LC beneficiary; there is no open `block` finding; every waiver is valid (no authenticated waiver record exists yet, so any waiver is treated as invalid); and the sanctions screen has no hit. The authoritative engine is **Cedar** (`cedarpy`); a deterministic fallback evaluator supplies per-rule detail and **a disagreement between the two denies**. An engine error falls back to the evaluator, never to "allow".

### 4.7 Approval: signing and verification

The approval screen is built from `approval_render(state)`, a canonical dictionary of exactly what the approver is shown: findings, waivers, injection flags, FX options, **the chosen FX route**, the finance offer, payee, applicant, amount and policy result. `deal_hash = SHA-256(canonical_json(render))`.

The approver signs `canonical_json({deal_hash, approver_id, method, signed_at, nonce})` with **Ed25519**. Verification (`security/approval.py`, run in `human_approval` and again in `execute`):

1. the approver id is in the registry;
2. the hash of the **current** render equals the signed hash, so any change after signing (amount, payee, route, a finding) invalidates the approval;
3. the Ed25519 signature verifies over the bound metadata;
4. `signed_at` is within a 300 s replay window and not in the future.

If the approver picks a route other than the default, it is applied before verification, so the signature is checked against the render that included the choice. An unknown route id is refused (HTTP 400 at the API; fail closed in the graph). The payout amount stays the invoice total; the route is a signed instruction, not an input to any calculation (DECISIONS #26).

**Decline.** A resume without a signed approval means the approver declined: the node records `declined` and the note, `after_approval` routes to `report`, and no payout runs.

**Execution.** `execute` re-verifies the signature, re-checks the policy result and the absence of open blocks, then takes a Redis lock keyed `payout:{deal_id}:{deal_hash}` (`SET NX`, 24 h) so a signed approval can pay out once. It calls `anchor_hash` and `execute_sandbox_payout` through a registry in which both tools are `act` tools with `llm_callable=False`, allowlisted to `execute`. It returns a receipt. A state invariant additionally forbids a receipt without an approval, an `allow` policy decision, and an absence of open blocks.

### 4.8 Audit chain

Each event is `{kind, deal_id, tenant_id, payload, ts}` and its hash is `SHA-256(prev_hash ‖ canonical_json(event))`, chained per tenant from a zero genesis. Events are written by hooks and by the tool registry, never by node code. In Postgres the table is append-only for the application role (UPDATE, DELETE and TRUNCATE revoked) and protected by row-level security on `tenant_id`. `GET /deals/{id}/audit` returns the events and `chain_ok`, the result of re-verifying the tenant's whole chain. The console shows this as "Review history verified".

At execution the current chain head is passed to an anchor client. **In this build the anchor is `MockAnchor`**, a deterministic in-process stand-in; a `FiscoBcosAnchor` class exists behind the same interface but is not wired in and has not been exercised against a node.

### 4.9 Deal copilot guard (DECISIONS #25)

`POST /deals/{id}/copilot` is a tool-less `fast` call. The server builds the deal record the model sees, with every amount pre-formatted from integer minor units. The question and earlier turns are wrapped in `<untrusted>`. Instruction-like questions are declined with no model call. **An answer that quotes a number (above 10) that is not in the record or the question fails closed** (HTTP 422) and the console falls back to a deterministic answer. Use is capped per deal (60 turns and 120,000 tokens by default, in memory) and is not charged to the pipeline budget, so chatting cannot trip a deal's kill switch. Each ask writes an audit event with the question's hash, not its text.

### 4.10 Budgets and the kill switch

Each deal has a budget (`harness/budget.py`): 64 steps, 400,000 tokens, USD 500 (defaults). The `before` hook checks it for every node and a breach sets a `fatal_error` that routes to `escalate`. Counters survive a resume. The budget object also has a kill switch that makes every later node fail closed; no HTTP endpoint exposes it yet.

---

## 5. Security design (summary)

The full treatment, with the permission tiers and the known-risk list, is in `SECURITY_SELF_ASSESSMENT.md`. In short:

- **Separation of duties.** Models read and write text; plain code routes, computes and acts; a person authorises. No model has tools in this implementation (the LLM client sends no tool definitions), and the only model-adjacent tool is a read-only document reader used by `verify`.
- **Untrusted input handling.** Uploads are type- and magic-byte-checked and size-capped (10 MB), stored once by SHA-256 as read-only files, parsed locally, screened, and always quarantined in prompts.
- **Authorisation of money movement.** A fresh Ed25519 signature over the exact rendered deal, checked twice, single-use, and bound to the chosen route.
- **Fail closed.** Every uncertain path escalates to a person.
- **Auditability.** Hash-chained, append-only, tenant-scoped, verifiable from the console.
- **Secret handling.** Provider keys live only in the LiteLLM proxy; the backend holds a spend-capped virtual key restricted to named model aliases.

**Honest boundary:** in the demo, the approval is signed by a **server-side demo signer** with a committed public key, the audit anchor is a mock, and the API has no authentication. These are described in the self-assessment as the main known risks.

---

## 6. Data model and persistence

| Store | Content | Notes |
|---|---|---|
| In-memory (default) | Deals, checkpoints, audit chain | Used by tests and bare `uvicorn` runs |
| PostgreSQL (`PERSIST_DEALS=true`, on in Compose) | `deal_snapshot` (with budget counters), `audit_event`, LangGraph checkpoint tables | The app connects as `cleartrade_app`; `app.current_tenant` is set per transaction so row-level security binds |
| Document store | Uploaded files, content-addressed by SHA-256, mode 0444 | A write to an existing hash is refused if the bytes differ |
| Valkey | Payout idempotency keys | If Redis is unreachable at start-up the runner falls back to an in-process stand-in (single process only) |

ORM tables also exist for `tenant`, `user`, `wechat_identity`, `trade_deal`, `document`, `finding`, `fx_quote`; the runner does not use `trade_deal`, `document` or `finding` yet (DECISIONS #21).

---

## 7. API

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness and environment |
| `POST /deals` | Create a deal (single synthetic tenant) |
| `POST /deals/demo-seed/{scenario}` | Create a deal from a demo scenario: `clean`, `discrepancy`, `mismatch`, `injection` |
| `POST /deals/{id}/documents`, `DELETE …/{doc_id}` | Upload (PDF, JPEG, PNG; 10 MB; magic-byte check) or remove a document |
| `POST /deals/{id}/readiness` | Extract documents without running the full review |
| `POST /deals/{id}/run` | Start the review. Returns 409 if a run is active or the deal is waiting for a decision |
| `GET /deals/{id}` | Current state |
| `GET /deals/{id}/stream` | SSE: `node_started`, `node_finished`, `interrupt`, `done`, `error`, `ping` |
| `POST /deals/{id}/resume` | Resume with `approve` (signed approval and optional `fx_route`), `reject` (with a note) or `corrected_document` |
| `POST /deals/{id}/sign_demo` | Demo only: the server signs the current render with the committed demo key. Returns 403 when the `env` setting is not `demo` (read from the variable `ENV`; the `CLEARTRADE_ENV` shown in `.env.example` is not read, see the self-assessment, R3) |
| `GET /deals/{id}/audit` | Audit events and chain verification result |
| `POST /deals/{id}/copilot` | Read-only Q&A about one deal |
| `/wechat/*` | WeChat adapter; mounted only when `feature_wechat` is on (off by default) |

Every response carries `synthetic_data: true`.

---

## 8. Web console

React 18 with TypeScript, TanStack Query and `EventSource`. Screens: a workspace with four one-click demo scenarios; a deal with Summary, Issues, Documents and a "More" menu (FX routes, Cash forecast, Review history); a five-step progress bar; an approval bar and confirm dialog; a copilot panel with conversation history stored in the browser. Model text is rendered as React text nodes (no raw HTML injection). A permanent synthetic-data badge is shown.

The approver chooses the payment route on the FX tab, and the estimated CNY proceeds appear in the approval banner and the confirm dialog. Documents read from an image are shown as **Unverified** with a "read from an image" chip. A held deal shows the server's reason, and a declined deal shows "You declined this deal, no payment made" with the note.

---

## 9. Deployment and configuration

- **Compose stack:** `make up` (production-style) or `make up-dev` (Vite hot reload). `make llm-key` creates the backend's spend-capped LiteLLM virtual key (default USD 10 per 30 days) restricted to the model aliases `reasoner`, `fast` and `vision`.
- **Model selection** is by environment: `LLM_PROVIDER`, `LLM_REASONER_MODEL`, `LLM_FAST_MODEL`, optional `LLM_VISION_MODEL`, and comma-separated `<PROVIDER>_API_KEYS`. `harness/litellm_render.py` renders the proxy config at start-up with one deployment per key (the router round-robins and cools down failing keys) and only `os.environ/` references, never secrets.
- **Timeouts:** the backend waits 90 s for text calls and 180 s for vision; the rendered proxy config sets 30 s for text deployments. A free reasoning model can exceed 30 s, so a long call may time out at the proxy (see §12).
- **Dev shim:** `backend/dev_proxy.py` is a development-only OpenAI-compatible shim that forwards to OpenRouter with a model fallback list. It is not part of the production design.
- **Showcase access:** `make tunnel` starts a Cloudflare Quick Tunnel to the web service and prints a temporary URL (DECISIONS #28). It adds public reachability to an app with no authentication, so it is for controlled showcases only.
- **Reproducibility:** pinned lockfile, image digests and seed data are described in `REPRODUCIBILITY.md`; the synthetic PDFs are generated deterministically and verified against committed checksums.

---

## 10. Testing and evaluation

| Layer | What it covers | Where |
|---|---|---|
| Unit | calculators (property-based plus hand-checked cases), rule checks, approval signing, audit chain, loaders, harness, renderer | `backend/tests/unit/` |
| Graph acceptance | Compiled-graph paths: clean deal to approval, fixable discrepancy to resolve, unfixable to escalate, injection to escalate, policy deny to escalate, approval rejected to report, FX route chosen, vision read | `backend/tests/graph/` |
| API | httpx ASGI tests of the routes, upload gate, resume, signing, run guard | `backend/tests/api/` |
| Integration | Postgres row-level security and append-only audit (environment-gated) | `backend/tests/integration/` |
| Eval | Metrics runner over the seed suite | `backend/tests/eval/` |
| Red team | promptfoo configuration with injection cases and clean controls | `evals/promptfoo/` |

**Quality gates** (`make gates`): `ruff`, `mypy` in strict mode, the full test suite, and `calc/` branch coverage with `--cov-fail-under=100`. They were run on the changes in this draft's period: ruff clean, `mypy` clean (59 source files), full backend test suite passing, web `tsc -b`, web build and the web unit tests passing. One pre-existing `ruff format --check` warning remains in `tests/graph/test_graph.py`.

**Offline evaluation** (seed suite with scripted extraction, last recorded 2026-10-17 in `PROGRESS.md`, not re-run for this draft): discrepancy recall 1.0, false alarms 0.0, workflow completion 1.0, calculation exactness 1.0, unauthorised actions 0. These use fake extraction, so they measure the deterministic core, not live-model accuracy.

**Live measurements in this period:** the vision results in §4.1; and, on the free text model, 20 to 37 s per document, which is slow against the 30 s proxy timeout (§12).

**Seed data:** 10 synthetic deals, 8 poisoned PDFs, four synthetic end-to-end lifecycle deals, all generated deterministically.

---

## 11. Changes since the earlier drafts

| Change | Pull request / commit | Effect |
|---|---|---|
| LC lifecycle rules, late-shipment and 21-day presentation checks, rule pack | #1, #3 | New deterministic checks and a `presentation_schedule` document kind (DECISIONS #17 to #19) |
| Competition pack and demo hardening | #2 | Demo scenarios, submission documents (note: some of those documents overstate the system, see the self-assessment's corrections) |
| Durable deals; injection flags in the signed render; grounded snippets; deal copilot; batch upload | commits `43ffbc0`, `111378a`, `4d46fea`, `88d7a9a`, `68b718a` | Postgres persistence, warn-level flags the approver must see, verbatim-quote enforcement, the copilot (DECISIONS #21, #22, #24, #25) |
| **Approver-selectable, signed FX route** | #4 | `selected_fx_route` in state; `fx_route` in the signed render; clickable route cards; estimated CNY proceeds shown at approval; run guard (409) on a deal waiting for a decision |
| **Vision reading of images and scanned PDFs** | #5 | `vision` alias; always-unverified result; image documents blocked at screening with a distinct reason; "Unverified" in the console (DECISIONS #27) |
| **Declined deals shown as declined** | #6 | `declined` and `decline_note` in state; report line; banner and header chip in the console |
| Showcase tunnel | `51d25e3` | Optional Cloudflare Quick Tunnel profile (DECISIONS #28) |
| Longer text-model timeout and dev-shim fallbacks | `cd8812b` | Backend text timeout 35 s to 90 s |
| Idempotency fallback | `5f8b50e` | If Redis is unreachable at start-up, an in-process stand-in is used |

---

## 12. Limitations and roadmap

**Known limitations (also tracked in the self-assessment):**

1. **No authentication or authorisation** on the API; one synthetic tenant (DECISIONS #14).
2. **Demo signer:** the console's approve path signs on the server with a committed public key. Real WebAuthn or WeChat SOTER signing is not implemented; the WeChat adapter is a disabled-by-default structural scaffold.
3. **Mock audit anchor.** No blockchain is involved in this build.
4. **Image and scanned documents always go to a person**; there is no "confirm these values" step yet.
5. **The Bangladesh import-tax calculator exists but is not part of the deal review.** Its rates are demo assumptions.
6. **Rule pack and quotes are demonstration data:** none of the 33 rules is marked verified against a primary source; the sanctions list, FX quotes and finance terms are synthetic.
7. **Free models are slow** (an image deal took 31 to 327 s; a text document 20 to 37 s) and the proxy's 30 s text timeout can cut a long call.
8. **Single process:** in-memory SSE queues and copilot counters; the checkpoint tables are not tenant-scoped.
9. **Injection screening scope:** hidden-text detection covers white text on a light page; the rule list is short; the classifier is a model and can be fooled. Defence in depth (deterministic checks, grounded quotes, human approval) is the real control.

**Roadmap, in priority order:** real approver authentication and client-side signing; a human "confirm these values" step for image documents; wiring the import-tax calculator and a verified rule pack; a real anchor (or removing the claim); API authentication, rate limiting and a CORS policy; pinned base images and a dependency scan in CI; a durable per-tenant copilot quota.
