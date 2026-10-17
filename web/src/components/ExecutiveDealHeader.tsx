import type { DealState } from "../api";
import { formatMoney } from "../api";
import { findPayee, totalAmountOf } from "../panels/Overview";
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Play,
  Lock,
  Building2,
  FileCheck2,
  PlaneTakeoff,
  Package,
} from "lucide-react";

interface ExecutiveDealHeaderProps {
  state: DealState;
  onNavigateTab?: (tab: string) => void;
  onRunDeal?: () => void;
  running?: boolean;
}

export default function ExecutiveDealHeader({
  state,
  onNavigateTab,
  onRunDeal,
  running = false,
}: ExecutiveDealHeaderProps) {
  const payee = findPayee(state);
  const applicant = findApplicant(state);
  const goods = findGoods(state);
  const amountMinor = totalAmountOf(state);

  const openBlocks = state.findings.filter(
    (f) => f.severity === "block" && f.status === "open",
  );
  const openWarns = state.findings.filter(
    (f) => f.severity === "warn" && f.status === "open",
  );

  const isExecuted = Boolean(state.receipt);
  const isEscalated = Boolean(state.escalation_reason);
  const hasDiscrepancy = openBlocks.length > 0 || Boolean(state.amendment_draft);
  const isReadyForApproval =
    !isExecuted && !isEscalated && !hasDiscrepancy && state.findings.length > 0;
  const isUnrun = state.extracted.length === 0 && !running;

  return (
    <div
      className="executive-deal-header"
      style={{
        background: "linear-gradient(180deg, rgba(22, 30, 41, 0.95) 0%, rgba(15, 23, 34, 0.95) 100%)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderRadius: "var(--radius, 10px)",
        padding: "20px 24px",
        marginBottom: 20,
        boxShadow: "0 8px 24px -4px rgba(0, 0, 0, 0.3)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 16,
        }}
      >
        {/* Deal Identity & Value */}
        <div style={{ flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.06em",
                color: "var(--accent-cyan, #06b6d4)",
                textTransform: "uppercase",
              }}
            >
              Export Trade Finance Pre-Flight
            </span>
            <span className="faint mono" style={{ fontSize: 11 }}>
              ID: {state.deal_id}
            </span>
          </div>

          <div
            style={{
              fontSize: 28,
              fontWeight: 800,
              letterSpacing: "-0.02em",
              color: "#f8fafc",
              marginBottom: 8,
              fontFamily: "var(--font-mono, monospace)",
            }}
          >
            {amountMinor !== null ? formatMoney(amountMinor, "USD") : "USD —"}
          </div>

          {/* Counterparties Route */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 13,
              color: "#cbd5e1",
              flexWrap: "wrap",
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <Building2 size={14} color="var(--accent-cyan, #06b6d4)" />
              <strong style={{ color: "#fff" }}>{payee ?? "Shenzhen Exporter"}</strong>
            </span>
            <ArrowRight size={13} color="var(--text-faint, #64748b)" />
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <Building2 size={14} color="var(--text-dim, #94a3b8)" />
              <span>{applicant ?? "Dhaka Trading House"}</span>
            </span>
          </div>

          {goods && (
            <div
              style={{
                marginTop: 6,
                fontSize: 12,
                color: "var(--text-dim, #94a3b8)",
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
              }}
            >
              <Package size={13} />
              <span>Goods: {goods}</span>
            </div>
          )}
        </div>

        {/* Status & Primary Action */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            justifyContent: "space-between",
            gap: 12,
            minWidth: 240,
          }}
        >
          {/* 1 Clear Status Badge */}
          {isExecuted && (
            <div
              className="chip chip-decision-allow"
              style={{ fontSize: 12, padding: "5px 12px", fontWeight: 700 }}
            >
              <CheckCircle2 size={14} />
              <span>Executed & Settled (Sandbox)</span>
            </div>
          )}

          {isEscalated && (
            <div
              className="chip chip-sev-block"
              style={{ fontSize: 12, padding: "5px 12px", fontWeight: 700 }}
            >
              <ShieldAlert size={14} />
              <span>Deal Escalated (Failed Closed)</span>
            </div>
          )}

          {hasDiscrepancy && (
            <div
              className="chip chip-sev-warn"
              style={{ fontSize: 12, padding: "5px 12px", fontWeight: 700 }}
            >
              <AlertTriangle size={14} />
              <span>Action Required ({openBlocks.length} Discrepancy)</span>
            </div>
          )}

          {isReadyForApproval && (
            <div
              className="chip"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "var(--status-pass, #10b981)",
                border: "1px solid rgba(16, 185, 129, 0.4)",
                fontSize: 12,
                padding: "5px 12px",
                fontWeight: 700,
              }}
            >
              <CheckCircle2 size={14} />
              <span>Verification Passed — Ready to Sign</span>
            </div>
          )}

          {isUnrun && (
            <div
              className="chip"
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                color: "var(--text-dim, #94a3b8)",
                border: "1px solid var(--border-subtle, #334155)",
                fontSize: 12,
                padding: "5px 12px",
              }}
            >
              <span>Ready for Verification</span>
            </div>
          )}

          {/* Contextual Action Button */}
          {hasDiscrepancy && (
            <button
              className="btn btn-primary"
              onClick={() => onNavigateTab?.("findings")}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, padding: "8px 16px" }}
            >
              <span>Review Discrepancy in Findings</span>
              <ArrowRight size={14} />
            </button>
          )}

          {isReadyForApproval && (
            <button
              className="btn btn-approve"
              onClick={() => onNavigateTab?.("overview")}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, padding: "8px 16px" }}
            >
              <Lock size={14} />
              <span>Sign Cryptographic Approval</span>
            </button>
          )}

          {isUnrun && onRunDeal && (
            <button
              className="btn btn-primary"
              onClick={onRunDeal}
              disabled={running}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, padding: "8px 16px" }}
            >
              <Play size={14} />
              <span>Run Pre-Flight Pipeline</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function findApplicant(state: DealState): string | null {
  for (const d of state.extracted) {
    const a = d.fields.find((f) => f.name === "applicant" || f.name === "buyer");
    if (a && a.value) return String(a.value);
  }
  return null;
}

function findGoods(state: DealState): string | null {
  for (const d of state.extracted) {
    const g = d.fields.find(
      (f) =>
        f.name === "goods_description" ||
        f.name === "description_of_goods" ||
        f.name === "goods",
    );
    if (g && g.value) return String(g.value);
  }
  return null;
}
