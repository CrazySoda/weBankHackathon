import { useState } from "react";
import type { DealState, InterruptPayload } from "../api";
import { api, formatMoney } from "../api";
import { findPayee, findApplicant, totalAmountOf, bestRoute } from "../panels/Overview";
import {
  AlertTriangle,
  Lock,
  AlertOctagon,
  CheckCircle2,
  X,
  ArrowRight,
} from "lucide-react";

interface ApprovalBarProps {
  state: DealState;
  payload: InterruptPayload | null;
  onResumed: () => void;
  onNavigateTab?: (tab: string) => void;
  currentTab?: string;
}

export default function ApprovalBar({
  state,
  payload,
  onResumed,
  onNavigateTab,
  currentTab,
}: ApprovalBarProps) {
  const kind =
    payload?.kind ??
    (payload === null ? inferKind(state) : String(payload.kind));

  if (kind === "await_corrected_doc") {
    return (
      <AwaitDocBanner
        state={state}
        onResumed={onResumed}
        onNavigateTab={onNavigateTab}
      />
    );
  }
  if (kind === "escalate" || state.escalation_reason) {
    return <EscalateBanner onNavigateTab={onNavigateTab} currentTab={currentTab} />;
  }
  return <ApprovalActionBanner state={state} payload={payload} onResumed={onResumed} />;
}

function inferKind(state: DealState): string {
  if (state.amendment_draft) return "await_corrected_doc";
  if (state.escalation_reason) return "escalate";
  return "human_approval";
}

/* ------------------------------------------------------------------ */
/* 1. Awaiting Corrected Doc Sleek Banner                             */
/* ------------------------------------------------------------------ */

function AwaitDocBanner({
  state,
  onNavigateTab,
}: {
  state: DealState;
  onResumed: () => void;
  onNavigateTab?: (tab: string) => void;
}) {
  const openBlocks = state.findings.filter(
    (f) => f.severity === "block" && f.status === "open",
  );

  return (
    <div
      className="clean-status-banner"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "12px 18px",
        background: "rgba(245, 158, 11, 0.08)",
        border: "1px solid rgba(245, 158, 11, 0.35)",
        borderRadius: "var(--radius, 8px)",
        marginBottom: 16,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 260, flex: 1 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "rgba(245, 158, 11, 0.15)",
            color: "var(--status-warn, #f59e0b)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <AlertTriangle size={18} />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--status-warn, #f59e0b)" }}>
              An update is needed
            </span>
            <span className="chip chip-sev-warn" style={{ fontSize: 10 }}>INTERRUPT</span>
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "#e2e8f0" }}>
            {openBlocks.length > 0 && openBlocks[0].summary
              ? `${openBlocks[0].summary}. An amendment draft has been prepared.`
              : "Commercial invoice amount exceeds LC limit. An amendment draft is ready."}
          </p>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          className="btn btn-primary"
          onClick={() => onNavigateTab?.("findings")}
          style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, padding: "8px 14px" }}
        >
          <span>View suggested fix</span>
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 2. Fail-Closed Escalated Sleek Banner                              */
/* ------------------------------------------------------------------ */

function EscalateBanner({
  onNavigateTab,
  currentTab,
}: {
  onNavigateTab?: (tab: string) => void;
  currentTab?: string;
}) {
  return (
    <div
      className="clean-status-banner"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "12px 18px",
        background: "rgba(244, 63, 94, 0.08)",
        border: "1px solid rgba(244, 63, 94, 0.35)",
        borderRadius: "var(--radius, 8px)",
        marginBottom: 16,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 260, flex: 1 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "rgba(244, 63, 94, 0.15)",
            color: "var(--status-block, #f43f5e)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <AlertOctagon size={18} />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--status-block, #f43f5e)" }}>
              This review needs a closer look
            </span>
            <span className="chip chip-sev-block" style={{ fontSize: 10 }}>ON HOLD</span>
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "#cbd5e1" }}>
            A person needs to review this deal before it can continue. Check the supporting documents and review history for next steps.
          </p>
        </div>
      </div>

      {currentTab !== "audit" && <button
        className="btn btn-secondary"
        onClick={() => onNavigateTab?.("audit")}
        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}
      >
        <span>View review history</span>
        <ArrowRight size={14} />
      </button>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 3. Human Approval Sleek Banner & Modal                             */
/* ------------------------------------------------------------------ */

function ApprovalActionBanner({
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
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  const payee = typeof payload?.payee === "string" ? payload.payee : findPayee(state);
  const approvalApplicant = payload && "applicant" in payload ? payload.applicant : undefined;
  const applicant = typeof approvalApplicant === "string"
    ? approvalApplicant
    : approvalApplicant === null ? null : findApplicant(state);
  const approvalAmount = payload && "amount_minor" in payload ? payload.amount_minor : undefined;
  const amountMinor = typeof approvalAmount === "number"
    ? approvalAmount
    : approvalAmount === null ? null : totalAmountOf(state);
  const paymentDetailsValid = !!applicant && !!payee && amountMinor !== null && amountMinor > 0;
  const best = bestRoute(state);

  const openBlocks = state.findings.filter(
    (f) => f.severity === "block" && f.status === "open",
  );
  const canApprove = openBlocks.length === 0 && busy === null && paymentDetailsValid;

  async function executeApprove() {
    setBusy("approve");
    setError(null);
    setShowConfirmModal(false);
    try {
      const res = await api.signDemo(state.deal_id);
      await api.resume(state.deal_id, {
        action: "approve",
        approval: res.approval,
        note: note || "Approved via DEMO signer (Ed25519 signature over canonical deal hash)",
      });
      onResumed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function executeReject() {
    if (!note.trim()) {
      setError("Please provide a rejection note explaining why this deal is declined.");
      return;
    }
    setBusy("reject");
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
    <>
      <div
        className="clean-status-banner"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          padding: "14px 18px",
          background: "rgba(16, 185, 129, 0.08)",
          border: "1px solid rgba(16, 185, 129, 0.35)",
          borderRadius: "var(--radius, 8px)",
          marginBottom: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 260, flex: 1 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "rgba(16, 185, 129, 0.15)",
              color: "var(--status-pass, #10b981)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Lock size={18} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: paymentDetailsValid ? "var(--status-pass, #10b981)" : "var(--status-warn, #f59e0b)" }}>
                {paymentDetailsValid ? "Ready for your approval" : "Payment details need review"}
              </span>
              <span className="chip chip-decision-allow" style={{ fontSize: 10 }}>SAMPLE DEAL</span>
            </div>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: "#e2e8f0" }}>
              Paying to: <strong>{payee ?? "Not identified"}</strong> · Amount:{" "}
              <strong>{amountMinor !== null && amountMinor > 0 ? formatMoney(amountMinor, "USD") : "Unavailable"}</strong>
              {best && (
                <span className="faint" style={{ marginLeft: 8 }}>
                  (Suggested route: {best.provider})
                </span>
              )}
            </p>
            {!paymentDetailsValid && (
              <p role="alert" style={{ margin: "6px 0 0", color: "var(--status-warn, #f59e0b)", fontSize: 12 }}>
                Approval is disabled until the buyer, seller, and a positive invoice amount are available.
              </p>
            )}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <input
            style={{ width: 220, fontSize: 12, padding: "6px 10px" }}
            placeholder="Add a note (optional)…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button
            className="btn btn-approve"
            disabled={!canApprove}
            onClick={() => setShowConfirmModal(true)}
            style={{ fontSize: 13, padding: "8px 16px" }}
          >
            {busy === "approve" ? "Approving…" : "Approve sample deal"}
          </button>
          <button
            className="btn btn-reject"
            disabled={busy !== null}
            onClick={executeReject}
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            {busy === "reject" ? "Declining…" : "Decline"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ margin: "-8px 0 16px", color: "var(--status-block)", fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div
          className="modal-overlay"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            className="modal-card"
            style={{
              background: "var(--bg-card, #0f172a)",
              border: "1px solid var(--border-subtle, #334155)",
              borderRadius: 10,
              maxWidth: 500,
              width: "100%",
              padding: 24,
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
                <CheckCircle2 color="var(--status-pass, #10b981)" size={20} />
                Approve this sample deal
              </h3>
              <button
                className="btn-link"
                onClick={() => setShowConfirmModal(false)}
                style={{ color: "#94a3b8", cursor: "pointer" }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.5, margin: "0 0 16px" }}>
              Please check the payment details below. This demo approval uses a sample signer and does not move real money.
            </p>

            <div style={{ background: "rgba(0, 0, 0, 0.35)", borderRadius: 6, padding: 12, marginBottom: 16 }}>
              <dl className="kv" style={{ margin: 0, fontSize: 12 }}>
                <dt>Paying</dt>
                <dd>{applicant ?? "Not identified"}</dd>
                <dt>Receiving</dt>
                <dd>{payee ?? "—"}</dd>
                <dt>Payment amount</dt>
                <dd style={{ fontWeight: 600, color: "var(--status-pass, #10b981)" }}>
                  {amountMinor !== null && amountMinor > 0 ? formatMoney(amountMinor, "USD") : "Unavailable"}
                </dd>
              </dl>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowConfirmModal(false)}
                disabled={busy !== null || !paymentDetailsValid}
              >
                Cancel
              </button>
              <button
                className="btn btn-approve"
                onClick={executeApprove}
                disabled={busy !== null}
              >
                {busy === "approve" ? "Signing…" : "Confirm & Sign"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
