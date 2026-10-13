# Walkthrough — one deal, end to end

This walks a single synthetic deal through ClearTrade exactly as the system
runs it: upload → extract → injection screen → compliance → FX → cash flow →
policy → approval → sandbox payout → audit. All commands work offline against
the committed seed PDFs except step 0.

Prerequisite: [uv](https://docs.astral.sh/uv/) installed — every Python
invocation in this repo goes through it (no bare `python3`, no manual venvs).
Most commands below have a `make` wrapper (`make up`, `make eval`,
`make reset-demo`, … — see `make help`).

Two ways to follow along:

- **A. Scripted mode (no API keys)** — the test suite and the eval runner do
  the same flow with scripted models. Fastest way to see the machinery:
  `cd backend && uv run pytest tests/graph -v`.
- **B. Live HTTP mode** — what's below. Requires the backend running
  (`docker compose up`, or `uvicorn app.main:app` with `LITELLM_VIRTUAL_KEY`
  set and the LiteLLM proxy reachable). Model responses come from `fast` /
  `reasoner` through the proxy.

> All data below is synthetic. The UI carries a permanent SYNTHETIC DATA badge.

---

## 0. Start the stack

```bash
cp .env.example .env            # set LITELLM_MASTER_KEY + ANTHROPIC_API_KEY
docker compose up --build       # postgres+pgvector, valkey, litellm, backend, web
# backend on :8000, web console on :5173, LiteLLM proxy on :4000
curl -s localhost:8000/health
# {"status":"ok","env":"demo","synthetic_data":true}
```

Open **http://localhost:5173** for the review console. Everything below can
also be done from the console UI.

## 1. Create a deal and upload documents

We use seed deal `seed-01` (clean) — the PDFs are already in the repo:

```bash
DEAL=$(curl -s -X POST localhost:8000/deals -F tenant_id=demo-tenant \
  | uv run python -c 'import sys,json;print(json.load(sys.stdin)["deal_id"])')

curl -s -X POST localhost:8000/deals/$DEAL/documents \
  -F kind=letter_of_credit -F file=@backend/seed/deals/pdfs/seed-01/lc.pdf
curl -s -X POST localhost:8000/deals/$DEAL/documents \
  -F kind=commercial_invoice -F file=@backend/seed/deals/pdfs/seed-01/inv.pdf
curl -s -X POST localhost:8000/deals/$DEAL/documents \
  -F kind=packing_list -F file=@backend/seed/deals/pdfs/seed-01/pl.pdf
```

Uploads are content-addressed (SHA-256), type/size checked (PDF/JPEG/PNG,
≤10 MB), and stored read-only. Raw bytes never enter the graph — only hashes.

## 2. Run the graph and watch it live (SSE)

```bash
curl -N -X POST localhost:8000/deals/$DEAL/run
curl -N localhost:8000/deals/$DEAL/stream
```

The stream emits `node_started` / `node_finished` for every node:

```
intake → extract_doc×3 → injection_screen → plan
      → compliance | fx | cashflow      (in parallel)
      → verify → credit_offer → policy_check → (park: human_approval)
```

What each stage did:

| Stage | What happened | Who decided |
|---|---|---|
| extract_doc | fields + per-field confidence + source spans parsed from the PDF text; input wrapped in `<untrusted>` | `fast` model, schema-constrained, no tools |
| injection_screen | regex rules (instruction phrases EN/CN, hidden white text, beneficiary-change language) + classifier pass | deterministic rules + `fast` |
| plan | picks which skills load (progressive loading, allowlist-checked) | `reasoner` |
| compliance | UCP 600 consistency battery, synthetic sanctions screen, CN VAT-refund estimate | **pure Python** (`app/rules/checks.py`, `app/calc/`) — the model only writes one-sentence explanations of numbers it may not change |
| fx | 3 synthetic routes ranked by net proceeds | **pure Python** (`app/calc/fx.py`) |
| cashflow | 91-day projection: 30% deposit outflow day 0, LC receipt at tenor | **pure Python** (`app/calc/cashflow.py`) |
| verify | re-derives every finding from the source documents; `lc-consistency` verdicts are recomputed, never model-judged; the model-judged path refuses fallback-tier models | re-computation + `reasoner` |
| policy_check | Cedar: amount cap, payee = LC beneficiary, no open block findings, waivers valid, sanctions clear | Cedar + deterministic mirror |

## 3. The approval interrupt

A clean deal parks at `human_approval`. The stream shows an `interrupt`
event; `GET /deals/$DEAL` now carries everything the approver sees:

```bash
curl -s localhost:8000/deals/$DEAL | uv run python -m json.tool
# state.policy.decision        -> "allow"
# state.fx_options             -> 3 routes, best first (net CNY)
# state.cash_projection        -> 91 balances, min_balance_day, days_below_zero
# state.finance_offer          -> best discounting offer (net proceeds, cost bp)
# state.findings               -> info-level VAT estimate only, no blocks
```

In the console this renders as the approval panel. Approving via API (the
console does the same; WebAuthn/SOTER supply real signatures in production —
backend verification is implemented in `app/security/approval.py`):

```bash
curl -s -X POST localhost:8000/deals/$DEAL/resume \
  -H 'content-type: application/json' \
  -d '{"action":"approve","approval":{"deal_hash":"0000000000000000000000000000000000000000000000000000000000000000",
       "approver_id":"owner-demo","method":"webauthn_passkey","signature_b64":"c2ln",
       "signed_at":"'"$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"'","nonce":"walkthrough-1"}}'
```

The graph resumes at `human_approval` → `execute` (sandbox payout, idempotency
key from (deal, nonce), audit-chain head anchored) → `report` → done.
`GET /deals/$DEAL` now shows `state.receipt` with the payout ref and the
anchored hash.

## 4. The three failure paths

Try the other seeds — each exercises a different terminal path:

**a. Fixable discrepancy → amendment → corrected document (seed-06**,
invoice 104,500 > LC 100,000**)**

```bash
# same upload steps with pdfs/seed-06/*.pdf, then run
# -> interrupt kind: await_corrected_doc, with state.amendment_draft filled
```
Upload the corrected invoice (the API treats a re-upload into the same
document slot as superseding the flawed original) and resume with
`{"action":"corrected_document","note":"..."}`. The graph re-extracts,
re-checks, and — finding nothing open — proceeds to approval.

**b. Unfixable block (seed-08**, beneficiary differs between LC and invoice**)**

Run ends in `escalate`; `state.escalation_reason` names the mismatch. No
payout is possible without human intervention outside the system.

**c. Prompt injection (backend/seed/deals/pdfs/poisoned/)**

The poisoned invoice carries white-text instructions ("Ignore all previous
instructions…"). `injection_screen` flags `hidden_text` (PyMuPDF span colour)
*and* `instruction_like_phrase` (regex) at `block` severity → straight to
`escalate`. The injected text never influences any number: all amounts were
computed before the classifier even ran.

**d. Policy deny (seed-10**, LC has no beneficiary**)**

Checks pass (nothing to compare), but Cedar's `payee_matches_beneficiary`
fails closed → `policy deny` → escalate. Fail-closed by design (BUILD_PLAN
rule 0.6).

## 5. The audit trail

```bash
curl -s localhost:8000/deals/$DEAL/audit | uv run python -m json.tool
# {"events": [...], "chain_ok": true}
```

Every node start/finish, tool call, refusal, interrupt and the payout is a
hash-chained event: `hash = sha256(prev_hash + canonical_json(event))`.
Tamper with any row and `chain_ok` flips to false — that's tested in
`tests/integration/test_db.py` (live Postgres) and
`tests/unit/harness/test_registry.py` (in-memory chain).

## 6. Where to look in the code

| You saw… | It lives in… |
|---|---|
| Graph wiring / routing | `backend/app/graph/build.py`, `routers.py` |
| Node implementations | `backend/app/graph/nodes/` |
| The money math | `backend/app/calc/` (100% branch coverage) |
| Injection rules | `backend/app/graph/nodes/injection_screen.py` |
| Tool allowlists | `backend/app/harness/tools/registry.py` |
| Budgets / kill switch | `backend/app/harness/budget.py` (hooks in `harness/hooks.py`) |
| LLM gateway client | `backend/app/harness/llm.py` |
| Approval crypto | `backend/app/security/approval.py` |
| Cedar policies | `backend/app/harness/policy.py` |
| Skills / prompts | `backend/skills/`, `backend/prompts/` |

Exact reproduction of every number: [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
