import { useRef, useState } from "react";
import type { DealState, DocKind, InterruptPayload } from "../api";
import { api, formatMoney } from "../api";
import { SeverityChip, StatusChip } from "../ui";
import { bestRoute, findPayee, totalAmountOf } from "../panels/Overview";

/**
 * Action bar rendered when the last event before done was an interrupt.
 * Two shapes, per the backend interrupt payloads:
 *  - human_approval: full approval panel (findings, waivers, fx, finance, payee, amount)
 *  - await_corrected_doc: amendment draft + corrected-document upload
 */
export default function ApprovalBar({
  state,
  payload,
  onResumed,
}: {
  state: DealState;
  payload: InterruptPayload | null;
  onResumed: () => void;
}) {
  const kind =
    payload?.kind ??
    (payload === null ? inferKind(state) : String(payload.kind));

  if (kind === "await_corrected_doc") {
    return <CorrectedDocBar state={state} payload={payload} onResumed={onResumed} />;
  }
  if (kind === "escalate") {
    return (
      <div className="action-bar" style={{ borderColor: "#7f1d1d" }}>
        <div className="action-bar-title" style={{ color: "#fca5a5" }}>
          Deal escalated — no action available
        </div>
        <div className="action-bar-sub">
          {state.escalation_reason ??
            "The harness failed closed. Review the findings and audit trail, then create a new deal."}
        </div>
      </div>
    );
  }
  return <HumanApprovalBar state={state} payload={payload} onResumed={onResumed} />;
}

function inferKind(state: DealState): string {
  if (state.amendment_draft) return "await_corrected_doc";
  if (!state.approval && !state.receipt && !state.escalation_reason) return "human_approval";
  return "human_approval";
}

/* ------------------------------------------------------------------ */

function HumanApprovalBar({
  state,
  payload,
  onResumed,
}: {
  state: DealState;
  payload: InterruptPayload | null;
  onResumed: () => void;
}) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const payee = (payload?.payee as string | null) ?? findPayee(state);
  const amountMinor =
    typeof payload?.amount_minor === "number"
      ? (payload.amount_minor as number)
      : totalAmountOf(state);
  const waivers = (payload?.waivers as Array<{ check_id: string }> | undefined) ??
    state.findings.filter((f) => f.status === "waived").map((f) => ({ check_id: f.check_id }));
  const findings = (payload?.findings as Array<DecisionLike> | undefined) ?? state.findings;
  const offer = (payload?.finance_offer as DealState["finance_offer"]) ?? state.finance_offer;
  const best = bestRoute(state);

  async function act(action: "approve" | "reject") {
    if (action === "approve") {
      setError("Approval is disabled until a registered passkey signer is configured.");
      return;
    }
    setBusy(action);
    setError(null);
    try {
      await api.resume(state.deal_id, { action: "reject", note });
      onResumed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="action-bar">
      <div className="action-bar-title">
        Human approval required
        <span className="chip chip-sev-warn">interrupt</span>
      </div>
      <div className="action-bar-sub">
        The harness paused before any payout. Review exactly what you are approving —
        the deal is hashed at approval time; any change after signing invalidates it.
      </div>

      <div className="card-grid" style={{ marginBottom: 12 }}>
        <div className="stat">
          <div className="label">Payee</div>
          <div className="value" style={{ fontSize: 15 }}>{payee ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">Amount</div>
          <div className="value">{amountMinor !== null ? formatMoney(amountMinor, "USD") : "—"}</div>
        </div>
        <div className="stat">
          <div className="label">Waivers</div>
          <div className="value">{waivers.length}</div>
          <div className="sub">each needs a named human + reason</div>
        </div>
        <div className="stat">
          <div className="label">Best FX route</div>
          <div className="value" style={{ fontSize: 15 }}>
            {best ? best.provider : "—"}
          </div>
          {best && (
            <div className="sub mono">
              net {formatMoney(best.net_minor, best.buy_currency)} · rate{" "}
              {(best.effective_rate_scaled / 1e6).toFixed(6)}
            </div>
          )}
        </div>
      </div>

      {offer && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h2>Finance offer</h2>
          <dl className="kv">
            <dt>Provider</dt>
            <dd>
              {offer.provider} {offer.synthetic && <span className="chip chip-synthetic">synthetic</span>}
            </dd>
            <dt>Face</dt>
            <dd>{formatMoney(offer.face.amount_minor, offer.face.currency)}</dd>
            <dt>Advance</dt>
            <dd>{formatMoney(offer.advance.amount_minor, offer.advance.currency)}</dd>
            <dt>Total cost</dt>
            <dd>{formatMoney(offer.total_cost.amount_minor, offer.total_cost.currency)}</dd>
            <dt>Net proceeds</dt>
            <dd>{formatMoney(offer.net_proceeds.amount_minor, offer.net_proceeds.currency)}</dd>
            <dt>Effective cost</dt>
            <dd>{offer.effective_cost_bp_annual} bp annual · {offer.days_to_maturity} days</dd>
          </dl>
        </div>
      )}

      <div className="card" style={{ marginBottom: 12 }}>
        <h2>Findings being approved ({findings.length})</h2>
        {findings.length === 0 ? (
          <div className="empty">No findings — clean deal.</div>
        ) : (
          findings.map((f, i) => (
            <div key={i} className={`finding sev-${f.severity}`} style={{ marginBottom: 8 }}>
              <div className="finding-head">
                <SeverityChip severity={f.severity} />
                <StatusChip status={f.status} />
                <span className="finding-rule">{f.rule_id}</span>
              </div>
              <div className="finding-summary" style={{ fontSize: 13 }}>
                {"summary" in f && typeof f.summary === "string" ? f.summary : ""}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="row">
        <input
          style={{ flex: 1, minWidth: 260 }}
          placeholder="Note (required for reject — why you are declining)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          className="btn btn-approve"
          disabled
          onClick={() => act("approve")}
        >
          Passkey approval unavailable
        </button>
        <button
          className="btn btn-reject"
          disabled={busy !== null}
          onClick={() => act("reject")}
        >
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>
        Approval requires a valid signature from a registered approver key. No demo signature is accepted.
      </p>
    </div>
  );
}

interface DecisionLike {
  check_id: string;
  rule_id: string;
  severity: "info" | "warn" | "block";
  status: "open" | "fixed" | "waived";
  summary?: string;
}

/* ------------------------------------------------------------------ */

function CorrectedDocBar({
  state,
  payload,
  onResumed,
}: {
  state: DealState;
  payload: InterruptPayload | null;
  onResumed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<DocKind>("commercial_invoice");
  const fileRef = useRef<HTMLInputElement>(null);

  const draft =
    (payload?.amendment_draft as string | null | undefined) ?? state.amendment_draft;
  const openBlocks =
    (payload?.open_block_findings as Array<{ rule_id: string; summary: string }> | undefined) ??
    state.findings
      .filter((f) => f.severity === "block" && f.status === "open")
      .map((f) => ({ rule_id: f.rule_id, summary: f.summary }));

  async function submit() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Attach the corrected document first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.uploadDocument(state.deal_id, file, kind);
      await api.resume(state.deal_id, {
        action: "corrected_document",
        note: `corrected document uploaded: ${file.name}`,
      });
      onResumed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-bar await-doc">
      <div className="action-bar-title">
        Corrected document required
        <span className="chip chip-sev-info">interrupt</span>
      </div>
      <div className="action-bar-sub">
        The harness drafted an amendment for the fixable discrepancies below.
        Attach the corrected document to resume — max 1 retry, then the deal escalates.
      </div>

      {openBlocks.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          {openBlocks.map((f, i) => (
            <div key={i} className="finding sev-block" style={{ marginBottom: 6 }}>
              <div className="finding-head">
                <SeverityChip severity="block" />
                <span className="finding-rule">{f.rule_id}</span>
              </div>
              <div className="finding-summary" style={{ fontSize: 13 }}>{f.summary}</div>
            </div>
          ))}
        </div>
      )}

      {draft ? (
        <>
          <h2 style={{ margin: "0 0 8px", fontSize: 13, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Amendment draft (text only — never sent automatically)
          </h2>
          <div className="amendment">{draft}</div>
        </>
      ) : (
        <div className="empty">No amendment draft available.</div>
      )}

      <div className="upload-row">
        <select value={kind} onChange={(e) => setKind(e.target.value as DocKind)}>
          <option value="commercial_invoice">Commercial invoice</option>
          <option value="letter_of_credit">Letter of credit</option>
          <option value="packing_list">Packing list</option>
          <option value="bill_of_lading">Bill of lading</option>
        </select>
        <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" />
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {busy ? "Uploading…" : "Upload corrected document & resume"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
