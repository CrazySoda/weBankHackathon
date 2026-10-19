import type { DealState } from "../api";
import { formatMoney } from "../api";
import ExecutiveDealHeader from "../components/ExecutiveDealHeader";
import {
  Building2,
  FileText,
  Receipt as ReceiptIcon,
  Globe,
  Package,
} from "lucide-react";

interface OverviewProps {
  state: DealState;
  onNavigateTab?: (tab: string) => void;
  onRunDeal?: () => void;
  running?: boolean;
}

export default function Overview({
  state,
  onNavigateTab,
  onRunDeal,
  running = false,
}: OverviewProps) {

  const openFindings = state.findings.filter((f) => f.status === "open");
  const blockCount = openFindings.filter((f) => f.severity === "block").length;
  const best = bestRoute(state);
  const payee = findPayee(state);
  const applicant = findApplicant(state);
  const lcNumber = findLcNumber(state);
  const goods = findGoods(state);

  return (
    <div className="overview-panel">
      {/* 1. Executive Deal Header (Hero Card) */}
      <ExecutiveDealHeader
        state={state}
        onNavigateTab={onNavigateTab}
        onRunDeal={onRunDeal}
        running={running}
      />

      {/* 2. Key Metrics Grid (4 Clean Cards) */}
      <div className="card-grid" style={{ marginBottom: 20 }}>
        <div
          className="stat"
          style={{ cursor: "pointer" }}
          onClick={() => onNavigateTab?.("documents")}
          title="Click to view submitted trade documents"
        >
          <div className="label">Documents</div>
          <div className="value tabular">{state.documents.length}</div>
          <div className="sub">
            {state.extracted.length} reviewed
          </div>
        </div>

        <div
          className="stat"
          style={{ cursor: "pointer" }}
          onClick={() => onNavigateTab?.("findings")}
          title="Click to view compliance discrepancies"
        >
          <div className="label">Open issues</div>
          <div
            className="value tabular"
            style={{
              color: blockCount > 0 ? "var(--status-block, #f43f5e)" : "var(--status-pass, #10b981)",
            }}
          >
            {openFindings.length}
          </div>
          <div className="sub">
            {blockCount > 0 ? `${blockCount} must be resolved` : "Nothing blocking this deal"}
          </div>
        </div>

        <div
          className="stat"
          style={{ cursor: "pointer" }}
          onClick={() => onNavigateTab?.("fx")}
          title="Click to view FX quotes and settlement comparison"
        >
          <div className="label">Payment options</div>
          <div className="value tabular">{state.fx_options.length}</div>
          <div className="sub">
            {best ? `Best: ${best.provider}` : "No active quotes"}
          </div>
        </div>

        <div
          className="stat"
          style={{ cursor: "pointer" }}
          onClick={() => onNavigateTab?.("cash")}
          title="Click to view the 90-day cash flow projection"
        >
          <div className="label">Cash forecast</div>
          <div className="value tabular">
            {state.cash_projection ? `${state.cash_projection.days_below_zero}d` : "—"}
          </div>
          <div className="sub">
            {state.cash_projection
              ? state.cash_projection.days_below_zero > 0
                ? "Working capital gap projected"
                : "Safe positive balance"
              : "Review this deal to see your forecast"}
          </div>
        </div>
      </div>

      {/* 3. Settlement & Payout Receipt (When Executed) */}
      {state.receipt && (
        <div className="card" style={{ padding: "20px 24px", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <ReceiptIcon size={18} color="var(--status-pass, #10b981)" />
            <h2 style={{ margin: 0, fontSize: 16 }}>Payment receipt</h2>
          </div>
          <dl className="kv" style={{ margin: 0 }}>
            <dt>Receipt number</dt>
            <dd className="mono">{state.receipt.receipt_id}</dd>
            <dt>Payment reference</dt>
            <dd className="mono">{state.receipt.payout_ref}</dd>
            <dt>Paid</dt>
            <dd className="mono" style={{ fontWeight: 700, color: "var(--status-pass, #10b981)", fontSize: 15 }}>
              {formatMoney(state.receipt.amount.minor, state.receipt.amount.currency)}
            </dd>
            <dt>Completed</dt>
            <dd className="mono">{state.receipt.executed_at}</dd>
          </dl>
        </div>
      )}

      {/* 4. Trade Counterparties & Goods Breakdown */}
      <div className="card" style={{ marginBottom: 20, padding: "20px 24px" }}>
        <h2 style={{ fontSize: 14, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim, #94a3b8)", margin: "0 0 16px" }}>
          This shipment
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          {/* Exporter */}
          <div style={{ background: "rgba(0, 0, 0, 0.2)", padding: 14, borderRadius: "var(--radius-sm, 6px)", border: "1px solid var(--border-subtle, #232d3b)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Building2 size={16} color="var(--accent-cyan, #06b6d4)" />
              <strong style={{ fontSize: 13, color: "#f8fafc" }}>Seller</strong>
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--accent-cyan, #06b6d4)", marginBottom: 4 }}>
              {payee ?? "Seller not identified"}
            </div>
            <div className="faint" style={{ fontSize: 12 }}>
              Location not provided
            </div>
          </div>

          {/* Importer */}
          <div style={{ background: "rgba(0, 0, 0, 0.2)", padding: 14, borderRadius: "var(--radius-sm, 6px)", border: "1px solid var(--border-subtle, #232d3b)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Globe size={16} color="var(--text-dim, #94a3b8)" />
              <strong style={{ fontSize: 13, color: "#f8fafc" }}>Buyer</strong>
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0", marginBottom: 4 }}>
              {applicant ?? "Buyer not identified"}
            </div>
            <div className="faint" style={{ fontSize: 12 }}>
              Location not provided
            </div>
          </div>

          {/* Instrument / Contract */}
          <div style={{ background: "rgba(0, 0, 0, 0.2)", padding: 14, borderRadius: "var(--radius-sm, 6px)", border: "1px solid var(--border-subtle, #232d3b)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <FileText size={16} color="var(--accent-violet, #8b5cf6)" />
              <strong style={{ fontSize: 13, color: "#f8fafc" }}>Payment terms</strong>
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", marginBottom: 4 }}>
              Letter of Credit {lcNumber ? `#${lcNumber}` : "(Document Attached)"}
            </div>
            <div className="faint" style={{ fontSize: 12 }}>
              Set out in the attached letter of credit
            </div>
          </div>
        </div>

        {goods && (
          <div
            style={{
              marginTop: 16,
              padding: "10px 14px",
              background: "rgba(255, 255, 255, 0.02)",
              borderRadius: "var(--radius-sm, 6px)",
              border: "1px solid rgba(255, 255, 255, 0.05)",
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 13,
            }}
          >
            <Package size={16} color="var(--text-dim, #94a3b8)" />
            <span style={{ color: "var(--text-dim, #94a3b8)" }}>Goods:</span>
            <span style={{ color: "#f8fafc", fontWeight: 500 }}>{goods}</span>
          </div>
        )}
      </div>

      {/* Subtle Synthetic Footnote */}
      <p className="faint" style={{ fontSize: 12, marginTop: 16, textAlign: "center" }}>
        All amounts, FX quotes, and trade calculations in this console are synthetic demonstration data for evaluation.
      </p>
    </div>
  );
}

export function findPayee(state: DealState): string | null {
  for (const d of currentExtracted(state)) {
    if (d.kind !== "commercial_invoice") continue;
    const b = d.fields.find((f) => f.name === "beneficiary");
    if (b && b.value !== null && b.value !== undefined) return String(b.value);
  }
  return null;
}

export function findApplicant(state: DealState): string | null {
  for (const d of currentExtracted(state)) {
    const a = d.fields.find((f) => f.name === "applicant" || f.name === "buyer");
    if (a && a.value) return String(a.value);
  }
  return null;
}

export function findLcNumber(state: DealState): string | null {
  for (const d of currentExtracted(state)) {
    const lc = d.fields.find((f) => f.name === "lc_number" || f.name === "credit_number");
    if (lc && lc.value) return String(lc.value);
  }
  return null;
}

export function findGoods(state: DealState): string | null {
  for (const d of currentExtracted(state)) {
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

export function findAmount(state: DealState): number | null {
  for (const d of currentExtracted(state)) {
    if (d.kind !== "commercial_invoice") continue;
    const minor = d.fields.find((f) => f.name === "total_amount_minor" || f.name === "amount_minor");
    if (minor) {
      const value = typeof minor.value === "number" ? minor.value : Number(minor.value);
      if (Number.isSafeInteger(value) && value >= 0) return value;
    }
    const major = d.fields.find((f) => f.name === "total_amount");
    if (major) {
      const parsed = majorAmountToMinor(major.value);
      if (parsed !== null) return parsed;
    }
  }
  return null;
}

export function majorAmountToMinor(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const normalized = String(value).trim().replace(/,/g, "").replace(/^(?:USD\s*|\$\s*)/i, "");
  const match = /^([+-]?)(\d+)(?:\.(\d{1,2}))?$/.exec(normalized);
  if (!match) return null;
  const minor = BigInt(match[2]) * 100n + BigInt((match[3] ?? "").padEnd(2, "0") || "0");
  const signed = match[1] === "-" ? -minor : minor;
  if (signed > BigInt(Number.MAX_SAFE_INTEGER) || signed < BigInt(Number.MIN_SAFE_INTEGER)) return null;
  return Number(signed);
}

function currentExtracted(state: DealState) {
  const order = new Map(state.documents.map((doc, index) => [doc.doc_id, index]));
  const latest = new Map<string, (typeof state.extracted)[number]>();
  for (const doc of [...state.extracted].sort((a, b) => (order.get(a.doc_id) ?? -1) - (order.get(b.doc_id) ?? -1))) {
    latest.set(doc.kind, doc);
  }
  return [...latest.values()].sort((a, b) => (order.get(a.doc_id) ?? -1) - (order.get(b.doc_id) ?? -1));
}

export function bestRoute(state: DealState) {
  if (state.fx_options.length === 0) return null;
  return state.fx_options.reduce((a, b) => (b.net_minor > a.net_minor ? b : a));
}

/** The route the approver picked, if it is still one of this deal's quotes; else the best. */
export function chosenRoute(state: DealState, selectedId: string | null | undefined) {
  const picked = selectedId ? state.fx_options.find((o) => o.route_id === selectedId) : undefined;
  return picked ?? bestRoute(state);
}

export function totalAmountOf(state: DealState): number | null {
  return findAmount(state);
}
