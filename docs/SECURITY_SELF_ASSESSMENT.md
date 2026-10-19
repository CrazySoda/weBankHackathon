# ClearTrade: Security Self-Assessment Report (first draft)

**Team:** Tech_Hoodie$ · **Topic:** E, SME Finance Copilot
**Competition:** 2026 Shenzhen International FinTech Competition (FinTechathon), International Track
**Draft date:** 2026-10-19 · **Assessed:** repository `main` at commit `051e40d`
**Type of assessment:** internal self-assessment by the authors, from a read-through of the code and the tests. It is **not** an independent audit or a penetration test.

> The brief asks this report for the **permission-tier implementation** and the **known-risk list**. They are §3 and §6. Everything is synthetic data in a sandbox; no real money can move.

---

## 1. Summary

**What is strong.** The design keeps authority away from models. Models read and write text only. Routing, money maths, policy and execution are plain code. A person authorises every payout with a signature over exactly what they were shown, and any change after signing voids it. Every uncertain path stops and escalates. Actions are recorded in a hash-chained, append-only log.

**What is not production-grade yet.** This build is a demonstration. The five risks that matter most:

| # | Residual risk | Why it matters |
|---|---|---|
| R1 | The API has **no authentication or authorisation**, and a public showcase tunnel can expose it | Anyone with the URL can create deals, read any deal by id, and run the demo signer |
| R2 | The approval in the console is signed by a **server-side demo key** whose private half is committed to the repository | In that path no human signs; the signature proves integrity, not identity |
| R3 | The setting documented as `CLEARTRADE_ENV` **is not read**, so the demo signer stays on unless `ENV=dev` is set | A documented safety switch does not do what it says (found during this review) |
| R4 | The audit **anchor is a mock** and WebAuthn or WeChat SOTER verification is not implemented | Earlier documents claimed more; see §8 |
| R5 | Models are untrusted but still read the documents, and the injection screen is a limited, partly model-based filter | The real protection is the layers after it, not the screen itself |

**Readiness statement.** Suitable for a controlled, synthetic-data demonstration. Not suitable for real customers or real funds until R1 to R4 are closed (§9).

---

## 2. System, assets and trust boundaries

```
 ┌─────────────────────────── untrusted ───────────────────────────┐
 │  uploaded files (PDF/PNG/JPG) · questions typed to the copilot · │
 │  approver notes · model output text                              │
 └───────────────┬──────────────────────────────────────────────────┘
                 │ type + magic-byte check, 10 MB cap, SHA-256, read-only store
 ┌───────────────▼───────── semi-trusted: model tier ──────────────┐
 │  extract_doc · injection classifier · plan · compliance text ·   │
 │  resolve_exception · verify adjudication · copilot               │
 │  (schema-only output, no tools, via LiteLLM proxy only)          │
 └───────────────┬──────────────────────────────────────────────────┘
                 │ validated state updates only
 ┌───────────────▼───────────── trusted code ──────────────────────┐
 │  routers · rule checks · calc/ · policy (Cedar) · hooks · budget │
 └───────────────┬──────────────────────────────────────────────────┘
                 │ signed approval required
 ┌───────────────▼──────────── authority tiers ────────────────────┐
 │  person signs  →  deterministic execute node  →  sandbox payout │
 └──────────────────────────────────────────────────────────────────┘
```

**Assets protected:** the integrity of the payout decision (amount, payee, route); the audit record; provider API keys; the confidentiality of deal data (synthetic here); availability and cost of the model gateway.

**Threat actors considered:** a malicious counterparty who controls a document's content; a person who can reach the API; a compromised or manipulated model; a mistaken or rushed approver; an operator mistake (for example leaving the demo signer on).

**Out of scope for this draft:** physical access, host compromise, denial of service at network level, and the security of the model providers themselves.

---

## 3. Permission tiers (implementation)

Capabilities are granted by tier. A lower tier can never obtain a higher tier's capability through the code paths below.

### 3.1 Tier table

| Tier | Principal | Granted | Explicitly denied | How it is enforced (code) |
|---|---|---|---|---|
| **T0** Untrusted content | Document text and images, copilot questions, notes | Nothing. Treated as data only | Being read as instructions; reaching any tool | `<untrusted>` wrapping in prompts; schema-only outputs; injection screen; verbatim-snippet check in `extract_doc`; the copilot declines instruction-like questions without a model call |
| **T1** Model nodes | `extract_doc`, injection classifier, `plan`, explanation text in `compliance`, `resolve_exception`, `verify` adjudication, `copilot` | Return one schema-validated JSON or text answer | Tools, network, database, file access, routing, money maths, approving | The LLM client (`harness/llm.py`) has **no tool parameter** and sends none. It is the only module that talks to a model endpoint, and only through the LiteLLM proxy. Output is Pydantic-validated with one repair retry, then the node fails closed. `verify` passes `allow_degraded=False`, so a lower-tier fallback model cannot adjudicate. |
| **T2** Deterministic compute | Routers, `fx`, `cashflow`, `credit_offer`, `policy_check`, the UCP 600 battery, `calc/` | Pure computation on the deal state | Side effects; model calls (except where listed under T1) | `calc/` is integer-only with `--cov-fail-under=100`; strict `mypy`; hooks validate every state update and reject writes to `deal_id` or `tenant_id`; a post-node invariant check (confidence range, no receipt without approval, allow policy and no open block) |
| **T3** Read tool | `verify` only | `read_source_doc` (read-only, PDF only, same deal only) | Any other tool | `ToolRegistry.call()` checks the node allowlist first; a violation raises `ToolRefused` and writes a `tool_refused` audit event |
| **T4** Human authority | The approver | Approve (with an optional route choice), or decline | Approving anything but the exact rendered deal | Ed25519 signature over the canonical render hash; hash re-checked against the current state; 300 s replay window; the approver id must be in the key registry (§5) |
| **T5** Act | The `execute` node only | `execute_sandbox_payout`, `anchor_hash` | Being called by a model, by any other node, or without T4 | Both tools are `side_effect="act"` with `llm_callable=False`; the `Tool` constructor raises if an act tool is made LLM-callable; allowlist is `{execute}`; preconditions in §5.3 |
| **Operator** | LiteLLM master key; database owner | Administer the gateway and schema | Not available to the backend | The backend holds only a spend-capped virtual key restricted to named aliases (`reasoner`, `fast`, `vision`); the app connects to Postgres as `cleartrade_app`, which row-level security and `REVOKE` bind (the owner role, a superuser in the local stack, bypasses RLS) |

### 3.2 Capability matrix

| Capability | T0 | T1 models | T2 code | T3 read | T4 human | T5 execute |
|---|---|---|---|---|---|---|
| Supply data to the system | yes | | | | | |
| Produce text for a person to read | | yes | | | | |
| Choose the next workflow step | | | yes | | | |
| Compute any money figure | | | yes | | | |
| Read a source document | | | | verify only | | |
| Authorise a payout | | | | | yes | |
| Move (simulated) money, anchor the audit head | | | | | | yes, with T4 |

### 3.3 Controls that bound every tier

- **Budget and kill switch:** per deal, 64 steps, 400,000 tokens and USD 500, enforced by the `before` hook for every node. A breach sets `fatal_error` and the deal escalates. Copilot use is capped separately (60 turns, 120,000 tokens).
- **Fail closed:** any exception inside a node becomes a `fatal_error`; every router checks it first; there is no path from an error to execution.
- **Audit:** every node start, finish, interrupt, failure, tool call and refusal is written by a hook or the registry, not by node code. The chain is described in the technical document (§4.8); its limits are R4 and R19.
- **Demo labelling:** every API response carries `synthetic_data: true`; the console shows a permanent badge.

---

## 4. Assessment against the OWASP Top 10 for LLM Applications (2025)

Ratings: **Effective** (a control exists and is tested), **Partial** (a control exists with a stated limit), **Gap** (not addressed in this build).

| ID | Risk | Controls in this build | Evidence | Rating | Residual |
|---|---|---|---|---|---|
| LLM01 | Prompt injection | Rules for instruction-like phrases (EN and ZH) and hidden white text; a `fast` classifier; `<untrusted>` quarantine; schema-only outputs; no tools for models; deterministic checks re-derive every finding; human approval | `graph/nodes/injection_screen.py`; graph tests with poisoned seed PDFs; `tests/unit/graph/test_routers.py` | **Partial** | The screen covers PDFs only; the phrase list is short; hidden-text detection finds near-white text on a light page, not tiny fonts or off-page text; the classifier is a model. A subtle change of a field value (not an instruction) is caught only by grounding, the deterministic battery and the approver. |
| LLM02 | Sensitive information disclosure | Provider keys only in the LiteLLM proxy; spend-capped virtual key; `.env` is git-ignored; copilot audit stores a question hash, not text; synthetic data only | `litellm_render.py` (only `os.environ/` references); `.gitignore`; copilot audit event | **Partial** | No authentication, so any caller who knows a deal id can read it (R1). Prompts carry deal text to the model provider. |
| LLM03 | Supply chain | Hash-locked `uv.lock`; LiteLLM pinned to v1.105.0 by digest (versions 1.82.7 and 1.82.8 are noted as malicious in the plan); Postgres, Valkey and cloudflared images pinned by digest | `uv.lock`; `docker-compose.yml` | **Partial** | The backend and web base images (`python:3.12-slim`, `node:18-alpine`, `nginx:1.27-alpine`) are tag-pinned, not digest-pinned; Node 18 is end-of-life; no dependency or image scan is evidenced in CI (R13). |
| LLM04 | Data and model poisoning | No fine-tuning; rules come from a curated, versioned seed pack, never generated at run time; prompts are versioned with a content hash | `backend/seed/rules/`; `harness/prompts/loader.py` | **Effective** for the design | The rule pack is not verified against primary sources (R14). |
| LLM05 | Improper output handling | Strict Pydantic schemas (`strict=True` for money); one repair retry then fail closed; model text rendered as React text nodes; the copilot rejects an answer containing numbers absent from the deal record; no model output reaches a shell, SQL or the payout | `harness/llm.py`; `api/copilot.py`; no `dangerouslySetInnerHTML` in `web/src` | **Effective** | The copilot's number check covers digits above 10 only; a wrong non-numeric statement can still appear (R18). |
| LLM06 | Excessive agency | Models have no tools; the only act tools are non-LLM-callable and bound to `execute`; execution needs a verified signature, an allow policy, no open blocks and an idempotency lock | `harness/tools/registry.py`; `graph/nodes/approval.py`; `test_registry.py` | **Effective** | The human path is demo-signed in the console (R2). |
| LLM07 | System prompt leakage | Prompts hold no secrets or credentials; keys are never in prompts; the API never returns prompts | `backend/prompts/` | **Effective** for secrets | Prompts are in the open-source repository by design; they are not confidential. |
| LLM08 | Vector and embedding weaknesses | pgvector is provisioned but no embedding retrieval is used by the pipeline | n/a | **Not applicable** | Revisit if retrieval is added. |
| LLM09 | Misinformation | Money and findings are computed by code; every extracted value is a verbatim quote with a confidence; `verify` re-derives findings; explanations are labelled; image-read values are labelled Unverified | `rules/checks.py`; `calc/`; `extract_doc.py` | **Partial** | Free models can misread or explain badly; plain-language explanations are model text. |
| LLM10 | Unbounded consumption | 10 MB upload cap; per-deal step, token and cost budgets; copilot caps; one deployment per key with cool-down; spend-capped virtual key | `config.py`; `harness/budget.py`; `litellm_render.py` | **Partial** | No request rate limiting; no limit on the number of deals or uploads per caller; copilot counters reset on restart (R6). |

---

## 5. Approval and execution protocol

### 5.1 Sequence

1. The graph reaches `human_approval` and pauses (an interrupt).
2. The console shows the approver the render: findings, injection flags, FX options, the chosen route, the finance offer, payee, amount and the policy result.
3. The approver chooses a route (default: best net) and approves or declines. On approval a signature is produced over `{deal_hash, approver_id, method, signed_at, nonce}`, where `deal_hash` is the SHA-256 of the canonical render.
4. `human_approval` verifies it (§5.2). A decline records `declined` and a note and goes to `report`; nothing is paid.
5. `execute` verifies it again, checks its preconditions, takes the idempotency lock, then anchors the audit head and runs the sandbox payout, producing a receipt.

### 5.2 Verification checks

Approver id known · hash of the **current** render equals the signed hash · Ed25519 signature valid over the bound metadata · `signed_at` within 300 s and not in the future · non-empty signature, hash, approver id and nonce · the render belongs to this deal · unknown FX route refused.

### 5.3 `execute` preconditions

A verified approval, a policy decision of `allow`, no open `block` finding, a payable amount, an available idempotency store, and a `SET NX` lock on `payout:{deal_id}:{deal_hash}:lock` (24 h). A state invariant also forbids a receipt without an approval, an allow decision and the absence of open blocks.

### 5.4 Attacks considered

| Attack | Result | Test |
|---|---|---|
| Replay an old approval | Rejected after 300 s | `test_replayed_approval_after_window_rejected` |
| Change amount, payee, applicant or a finding after signing | Hash mismatch; approval invalidated | `test_changed_amount_invalidates`, `test_changed_payee_invalidates`, `test_changed_applicant_invalidates`, `test_added_finding_invalidates` |
| Add or remove an injection flag after signing | Invalidated | `test_adding_a_flag_after_signing_invalidates_the_approval` |
| Swap the FX route after signing, or drop it at resume | Refused | `test_route_changed_after_signing_is_rejected`, `test_signed_choice_dropped_at_resume_is_rejected` |
| Unknown FX route | Refused (400 at the API, fail closed in the graph) | `test_unknown_route_fails_closed` |
| Signature by an unregistered key or unknown approver | Rejected | `test_unsigned_by_attacker_key_rejected`, `test_unknown_approver_rejected` |
| Empty signature or missing nonce | Rejected | `test_empty_signature_rejected`, `test_missing_nonce_rejected` |
| Submit the same signed approval twice | Second payout blocked by the idempotency lock | covered by the execution path; see R5 for the store's single-process fallback |
| A model attempts to call a payout tool | Cannot: models have no tools, and act tools are not LLM-callable | `test_act_tool_must_not_be_llm_callable`, `test_call_outside_allowlist_refused` |

### 5.5 What this protocol does **not** prove

In the demo path, `POST /deals/{id}/sign_demo` makes the **server** sign with the committed demo key. The signature proves the render was not altered; it does **not** prove a human decided. The signed record carries `method="demo_key"`, the response carries a notice, and the console labels it. It is refused when the `env` setting is not `demo`; that setting defaults to `demo` and is read from the variable **`ENV`**, not from the documented `CLEARTRADE_ENV` (R3). A real deployment must register approver keys through `APPROVAL_PUBLIC_KEYS_JSON` (which removes the demo key from the registry) and sign on the approver's device.

---

## 6. Known-risk register

Severity reflects impact in a real deployment. "Demo status" says what is true today. Open items are in §9.

| ID | Risk | Severity | Current mitigation | Residual and demo status | Planned fix |
|---|---|---|---|---|---|
| **R1** | No authentication or authorisation on any route; one synthetic tenant (DECISIONS #14); deal ids are the only handle. A public Cloudflare tunnel (`make tunnel`) makes the app reachable from the internet | **High** | Synthetic data; tunnel is opt-in and documented as showcase-only | **Open.** Anyone with the URL can create deals, read a deal, run the demo signer, and spend model budget | API authentication, per-tenant authorisation, and take the tunnel down outside demos |
| **R2** | Demo signer: committed private key, server-side signing, no human in that path | **High** | Labelled in response, UI and record (`demo_key`); refused outside demo; signature still bound to the render | **Open (by design for the demo).** Forgeable by anyone with the repository | Client-side signing (WebAuthn or SOTER) and a registered approver key |
| **R3** | The documented `CLEARTRADE_ENV` is not read by the settings; the real variable is `ENV`, default `demo`. Setting `CLEARTRADE_ENV=dev` leaves the demo signer enabled. Verified by running the settings loader with each variable | **High** | None. Found in this review | **Open.** Easy to misconfigure | Read `CLEARTRADE_ENV` (or fix the docs), and default to a non-demo mode |
| **R4** | The audit anchor is `MockAnchor`, hard-wired in the runner; a `FiscoBcosAnchor` class exists but is not wired or exercised. No WebAuthn or SOTER verification exists. The WeChat adapter is a structural scaffold, off by default | **Medium** | Honest labelling; tests assert the WeChat routes are disabled by default | **Open.** No on-chain evidence exists | Wire and test a real anchor, or drop the claim everywhere |
| **R5** | Idempotency: if Redis is unreachable at start-up, the runner silently uses an in-process stand-in. It does not survive a restart and does not span processes | **Medium** | Compose runs Valkey; the fallback only occurs if it is down | **Open.** A second process or a restart could allow a second payout for one approval | Fail start-up if Redis is required; add a database-backed lock |
| **R6** | No rate limiting; no CORS policy set; copilot caps and SSE queues are in memory | **Medium** | Upload cap; per-deal budgets; copilot per-deal caps | **Open.** Abuse and cost exposure if reachable (see R1) | Rate limits per client, explicit CORS, durable quotas |
| **R7** | Upload hardening: type and magic-byte check and size cap exist. The malware-scan call is only a hook point. PyMuPDF parses attacker-controlled PDFs | **Medium** | Content-addressed read-only store; local parsing; no document execution | **Partial.** Parser or decompression bombs are not specifically handled; oversize rejection (413) is not evidenced by an API test | Malware scan, page and size limits, parse in a sandbox |
| **R8** | Injection screening limits (see LLM01). A manipulated field value or a successful classifier evasion can reach the checks | **Medium** | Defence in depth: verbatim snippets, deterministic battery, `verify`, policy, human approval | **Partial** | Larger red-team corpus; run the promptfoo suite in CI; a visible-text-versus-image diff for PDFs |
| **R9** | Model quality and availability: free models are slow (20 to 37 s a text document; 31 to 327 s an image deal); the proxy's 30 s text timeout can cut long calls; the fallback chain is `reasoner` then `fast` | **Medium** | Longer client timeouts; `verify` refuses degraded models; failure escalates | **Partial.** Availability and consistency, not safety | Paid or hosted models with proper timeouts; align proxy and client timeouts |
| **R10** | Image and scanned documents are read by a vision model whose confidence is not trusted | **Medium** | Always labelled Unverified; always escalated; image documents blocked at screening | **By design.** No "confirm these values" step, so such a deal cannot be approved | A human confirmation step that signs the confirmed values |
| **R11** | Persistence limits: LangGraph checkpoint tables are not tenant-scoped; one process only; the owner role bypasses row-level security | **Medium** | The app role is bound by RLS and append-only grants; integration tests are environment-gated | **Partial.** Not multi-tenant safe | Tenant-scope the checkpoints; separate roles; multi-process lock |
| **R12** | Waivers: no authenticated waiver record exists, so any waiver fails policy | **Low** | Fail closed | **By design.** Waiving a finding is not possible in the demo | Authenticated waiver with a named person and reason |
| **R13** | Supply chain: base images not digest-pinned; Node 18 is end of life; no dependency or image scan evidenced in CI | **Medium** | `uv.lock` hashes; key images pinned | **Open** | Pin all images by digest, upgrade Node, add a scan to CI |
| **R14** | Rules and data are demonstrative: 33 rules, none verified against primary sources; HS tax rates are assumptions; the sanctions list, FX quotes and finance terms are synthetic; the Bangladesh import-tax calculator is not wired into the review | **Medium** | Labelled synthetic; sources recorded per rule | **Open.** Not valid for real compliance | Verify the pack; wire in the calculator; use real data feeds |
| **R15** | Secrets handling: local `.env` holds the master key and provider keys; the committed demo key is public by design | **Low** | `.env` git-ignored; keys never printed or logged by the tooling; virtual key spend-capped | **Partial.** Operator discipline | Secret manager for any non-local deployment |
| **R16** | Logging and privacy: audit payloads avoid raw document text; copilot logs a hash. Synthetic data only. No retention or deletion policy | **Low** | Summaries only in audit events | **Partial** | Retention and deletion policy before real data |
| **R17** | Approver experience: a rushed approver could approve without reading. The render lists findings and flags, but there is no forced acknowledgement of warnings | **Low** | The approver sees payee, amount, route and estimated proceeds; warnings are in the signed render | **Partial** | Require acknowledgement of each warning |
| **R18** | Copilot: a model-written answer. Only numbers above 10 are checked against the record; non-numeric claims are not | **Low** | Read-only; no tools; declined instruction-like questions; labelled "AI answer, checked against deal record"; per-deal caps | **Partial** | Extend checks to named entities and dates |
| **R19** | Audit anchor and chain: the chain detects tampering with stored events but is only as strong as its custody; the mock anchor adds no external evidence | **Low** | Append-only grants; chain verified from the console | **Partial** | External anchoring (see R4) |

---

## 7. Verification evidence

**Quality gates re-run on `main` at `051e40d` (2026-10-19, in a worktree on the same lockfile and venv):**

| Gate | Result |
|---|---|
| `ruff check` | Clean |
| `mypy` (strict) | Clean, 59 source files |
| Full backend test suite (`pytest tests`) | Passed (exit status 0): 411 passed, 12 skipped — the Postgres integration tests are environment-gated |
| `calc/` branch coverage | Gate enforces 100% (`--cov-fail-under=100`); measured 100.00% |
| Web `tsc -b`, `npm run build`, 10 unit tests (`npx vitest run`; there is no `npm test` script) | Passed |
| `ruff format --check` | One pre-existing warning in `tests/graph/test_graph.py` |

**Test areas relevant to security:** approval signing and tamper cases (`tests/unit/security`), FX route signing (`tests/graph/test_fx_route.py`), tool registry allowlists and `act`-tool rules (`tests/unit/harness/test_registry.py`), audit-chain tamper detection (`test_tamper_detected` in `tests/unit/harness/test_registry.py`), graph paths for injection, policy deny, rejection and escalation (`tests/graph`), API gates including the 415 type check, WeChat routes disabled by default and the demo signer's labelling and refusal outside demo (`tests/api`), Postgres row-level security and append-only audit (`tests/integration`, gated), and the seed and rule-pack tests.

**Not done, and not claimed:** an independent penetration test; a live run of the promptfoo red-team suite for this draft; load or denial-of-service testing; a dependency or container vulnerability scan; verification of the WeChat adapter against WeChat's servers; a test that exercises a real blockchain anchor.

**Offline evaluation** (scripted extraction, last recorded 2026-10-17, not re-run for this draft): discrepancy recall 1.0, false alarms 0.0, completion 1.0, calculation exactness 1.0, unauthorised actions 0. These measure the deterministic core, not live-model behaviour.

---

## 8. Corrections to earlier documents

The earlier `docs/SECURITY_SELF_ASSESSMENT_REPORT.md` contained statements this review could not support; this document replaces it. The pitch deck, demo video script, submission guide and presentation documents in `docs/` repeated several of the same claims and were **withdrawn from the repository on 2026-10-19** rather than corrected. The table records what each withdrawn statement got wrong.

| Earlier statement | What the code shows |
|---|---|
| "Status: Certified for Competition Review" | A self-assessment cannot certify; replace with "self-assessed, first draft" |
| Payout requires a "hardware-rooted" WebAuthn or SOTER signature | Not implemented. The console signs with a server-side demo key; the WeChat adapter checks structure only and is off by default |
| The chain head is "anchored into the FISCO BCOS consortium blockchain" | The runner uses `MockAnchor`. A FISCO client class exists but is not wired or tested |
| `injection_screen` analyses "visual layouts for zero-point fonts … suspicious unicode scripts" | Hidden-text detection covers near-white text on a light page. There is no zero-point-font or unicode-script check |
| "Strict tenant isolation enforced in all database queries" | Row-level security binds the app role on the listed tables; checkpoint tables are not tenant-scoped; one demo tenant exists |
| "Only two nodes (`verify` and `execute`) have tool access" | Accurate in effect: three tools are registered (`read_source_doc`; `execute_sandbox_payout` and `anchor_hash`) and models receive no tool definitions at all |
| "OWASP Top 10 for LLM (ASI01 to ASI10)" | ASI is the label of a different OWASP list (agentic applications); this report maps to the OWASP LLM Top 10 (2025) |
| Pitch and video documents: a USD 120,000 invoice, SWIFT MT707 amendments sent, hardware or biometric passkeys, FISCO BCOS anchoring, "90 seconds", "12 UCP checks" | The demo invoice is USD 104,500 against a USD 100,000 LC; amendments are drafted text only and never transmitted; see above for signing and anchoring; there are 7 deterministic LC checks plus a 33-rule pack; timing depends on the model |

---

## 9. Remediation plan

**Before the submission deadline (small, high value):**

1. Fix R3: make the demo-mode switch read `CLEARTRADE_ENV`, or change the documentation to `ENV`; keep the demo signer off unless explicitly enabled.
2. The overstated documents are withdrawn (§8); keep them out of anything a judge reads.
3. State R1, R2 and R4 plainly in the submission and the presentation (the deck's "honest limits" slide already covers the signer).
4. Do not leave the showcase tunnel running when not demonstrating.

**Next (to move toward a pilot):** API authentication and per-tenant authorisation (R1); client-side approver signing (R2); a database-backed idempotency lock and a start-up failure if Redis is required (R5); rate limits and a CORS policy (R6); a malware scan and parsing limits (R7); digest-pinned images, a Node upgrade and a CI scan (R13); a human confirmation step for image documents (R10).

**Later:** a verified rule pack and live data (R14); a real external anchor (R4); a larger red-team corpus in CI (R8); retention policy (R16).

---

## 10. Basis and limits of this report

Written by the project team from the code at `main` `051e40d`. The statements in §3 to §7 were checked against specific files and tests. Where a control is a design intent that is not implemented, it is listed as a gap. This report does not replace an independent review.
