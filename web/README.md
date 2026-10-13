# ClearTrade web review console

React + TypeScript (Vite) review console for ClearTrade — the human checkpoint
for pre-flighting a cross-border export deal. **All data shown is synthetic.**

## Run (dev)

```bash
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api/*` to the FastAPI
backend at `http://localhost:8000` (see `vite.config.ts`), so start the backend
first (`uvicorn app.main:app` from `backend/`, or `docker compose up backend`).

## Run (container)

```bash
docker compose up web   # builds this Dockerfile; compose maps port 5173 -> nginx:80
```

The multi-stage Dockerfile builds the bundle with `node:18-alpine` and serves
`dist/` from `nginx:1.27-alpine`, proxying `/api` to the `backend:8000`
container (SSE-safe: buffering off).

## What the console shows

- **Deal list (sidebar)** — create a deal (`POST /deals`), upload documents
  with a kind dropdown (`letter_of_credit`, `commercial_invoice`,
  `packing_list`, `bill_of_lading`). The red **SYNTHETIC DATA** badge is always
  visible top-right.
- **Overview** — state summary, policy decision card (per-rule pass/fail),
  receipt after execution, or the escalation reason.
- **Findings** — severity-sorted (`block` → `warn` → `info`) findings with
  status chips (`open`/`fixed`/`waived`), evidence quotes with document/page
  references, and the explanation text.
- **FX** — route comparison table (route, provider, net proceeds, effective
  rate, spread, fee); the best route by net proceeds is highlighted and every
  row carries a synthetic badge.
- **Cash flow** — hand-rolled SVG line chart of `daily_balance_minor` over the
  91-day horizon: axes, zero line, below-zero region shaded red, min-balance
  marker with a direct label, hover crosshair + tooltip, plus the events list.
- **Documents** — extracted fields with confidence bars (green/amber/red) and
  the source snippet each value came from.
- **Audit** — hash-chained event list (ts, kind, payload, short hash) with a
  green/red `chain_ok` indicator.

## Live streaming & human approval

Press **Run deal** to `POST /deals/{id}/run` and open an `EventSource` on
`/deals/{id}/stream`. Node starts/finishes stream into a live ticker; the deal
query is invalidated as events land.

When the final event before `done` is an **interrupt**, an action bar appears:

- `human_approval` — the full approval panel: findings being approved, waiver
  count, FX options, finance offer, payee and amount. **Approve** sends
  `POST /deals/{id}/resume` with a stub signed approval (`deal_hash` of zeros,
  `approver_id: owner-demo`, `method: webauthn_passkey`) — this demo signs in
  the browser with placeholder values; production uses a real WebAuthn
  passkey over the rendered deal hash. **Reject** resumes with
  `action: "reject"` and your note.
- `await_corrected_doc` — shows the amendment draft and lets you upload the
  corrected document, then resumes with `action: "corrected_document"`.

Money is rendered from integer minor units (`Intl.NumberFormat`, ÷100) —
never floats. Types for the whole `DealState` model live in `src/api.ts`.
