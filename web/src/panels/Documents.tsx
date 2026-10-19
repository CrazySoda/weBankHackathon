import type { DealState, ExtractedField } from "../api";
import { formatMoney } from "../api";
import { majorAmountToMinor } from "./Overview";
import { SyntheticChip, confidenceColor } from "../ui";
import {
  FileText,
  FileSpreadsheet,
  FileCheck,
  FileQuestion,
  AlertTriangle,
  UploadCloud,
  ArrowRight,
} from "lucide-react";

const KIND_META: Record<string, { label: string; icon: typeof FileText }> = {
  letter_of_credit: { label: "Letter of Credit", icon: FileCheck },
  commercial_invoice: { label: "Commercial Invoice", icon: FileText },
  packing_list: { label: "Packing List", icon: FileSpreadsheet },
  bill_of_lading: { label: "Bill of Lading", icon: FileText },
  presentation_schedule: { label: "Presentation Schedule", icon: FileCheck },
  unknown: { label: "Unknown document", icon: FileQuestion },
};

export default function Documents({ state, onAddDocuments }: { state: DealState; onAddDocuments?: () => void }) {
  const extracted = state.extracted;
  const unextracted = state.documents.filter(
    (d) => !extracted.some((e) => e.doc_id === d.doc_id),
  );

  if (state.documents.length === 0) {
    return (
      <div className="empty-state-panel documents-empty-state">
        <div className="empty-state-content">
          <div className="empty-state-icon"><UploadCloud size={25} strokeWidth={1.8} /></div>
          <span className="empty-state-kicker">Documents</span>
          <h2 className="empty-state-title">Bring your trade paperwork together</h2>
          <p className="empty-state-copy">
            Add the files for this deal. We’ll organize the key details so they’re easy to review.
          </p>
          {onAddDocuments && (
            <button className="empty-state-button" onClick={onAddDocuments}>
              Add documents <ArrowRight size={16} />
            </button>
          )}
          <div className="empty-state-footnote">PDF, PNG, and JPG files are supported</div>
        </div>
        <div className="empty-doc-checklist" aria-label="Suggested documents">
          <span><FileCheck size={15} /> Letter of credit</span>
          <span><FileText size={15} /> Commercial invoice</span>
          <span><FileSpreadsheet size={15} /> Packing list</span>
        </div>
      </div>
    );
  }

  return (
    <div className="documents-panel" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {extracted.map((doc) => {
        const meta = KIND_META[doc.kind] ?? KIND_META.unknown;
        const DocIcon = meta.icon;
        return (
          <div className="card doc-block" key={doc.doc_id} style={{ padding: 18 }}>
            <div className="doc-head" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
              <DocIcon size={18} style={{ color: "var(--accent-cyan, #06b6d4)" }} />
              <span className="doc-filename" style={{ fontWeight: 600, fontSize: 15 }}>
                {filenameFor(state, doc.doc_id)}
              </span>
              <span className="chip chip-sev-info">
                <DocIcon size={12} aria-hidden="true" />
                <span>{meta.label}</span>
              </span>
              {doc.low_confidence && (
                <span className="chip chip-sev-warn">
                  <AlertTriangle size={12} aria-hidden="true" />
                  <span>{doc.extraction_model.startsWith("vision:") ? "read from an image" : "low confidence"}</span>
                </span>
              )}
              <SyntheticChip />
            </div>

            {doc.extraction_model.startsWith("vision:") && (
              <div role="note" className="faint" style={{ fontSize: 12, marginBottom: 12, color: "var(--status-warn, #f59e0b)" }}>
                A vision model read these values from an image. They are not checked against any document
                text, so a person must confirm them.
              </div>
            )}

            {doc.fields.length === 0 ? (
              <div className="empty">No fields extracted from this document.</div>
            ) : (
              <div className="fields-table-wrapper" style={{ overflowX: "auto" }}>
                <table className="fields-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle, #334155)", textAlign: "left", color: "#94a3b8" }}>
                      <th style={{ padding: "8px 10px", width: "24%" }}>Detail</th>
                      <th style={{ padding: "8px 10px", width: "28%" }}>Information found</th>
                      <th style={{ padding: "8px 10px", width: "20%" }}>How sure</th>
                      <th style={{ padding: "8px 10px", width: "28%" }}>Source text</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.fields.map((f, i) => (
                      <FieldRow
                        key={i}
                        field={f}
                        fromImage={doc.extraction_model.startsWith("vision:")}
                        currency={String(doc.fields.find((candidate) => candidate.name === "currency")?.value ?? "USD")}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      {unextracted.map((d) => {
        const meta = KIND_META[d.kind] ?? KIND_META.unknown;
        const DocIcon = meta.icon;
        return (
          <div className="card doc-block" key={d.doc_id} style={{ opacity: 0.75, padding: 16 }}>
            <div className="doc-head" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
              <DocIcon size={16} />
              <span className="doc-filename" style={{ fontWeight: 600 }}>{d.filename}</span>
              <span className="chip chip-sev-info">
                <DocIcon size={12} aria-hidden="true" />
                <span>{meta.label}</span>
              </span>
              <span className="chip chip-status-open">not extracted</span>
              <span className="faint" style={{ fontSize: 11 }}>{formatFileSize(d.size_bytes)}</span>
            </div>
            <div className="faint" style={{ fontSize: 12 }}>
              We’ll read this document when you choose “Review deal”.
            </div>
          </div>
        );
      })}
    </div>
  );
}

function filenameFor(state: DealState, docId: string): string {
  return state.documents.find((d) => d.doc_id === docId)?.filename ?? docId;
}

function FieldRow({
  field,
  currency,
  fromImage = false,
}: {
  field: ExtractedField;
  currency: string;
  /** Read from an image: the model's own confidence is not trusted, so none is shown. */
  fromImage?: boolean;
}) {
  const pct = Math.round(field.confidence * 100);
  const color = confidenceColor(field.confidence);
  const value = formatFieldValue(field, currency);

  return (
    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
      <td style={{ padding: "8px 10px", fontWeight: 500, color: "#e2e8f0" }}>
        {humanizeFieldName(field.name)}
      </td>
      <td style={{ padding: "8px 10px", color: "var(--text-main, #f8fafc)" }}>
        {value}
      </td>
      <td style={{ padding: "8px 10px" }}>
        {fromImage ? (
          <span className="faint" style={{ fontSize: 12 }}>Unverified</span>
        ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              flex: 1,
              height: 6,
              background: "rgba(255,255,255,0.08)",
              borderRadius: 3,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${pct}%`,
                height: "100%",
                background: color,
                borderRadius: 3,
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <span
            className="mono"
            style={{
              fontSize: 11,
              fontWeight: 600,
              color,
              minWidth: 34,
              textAlign: "right",
            }}
          >
            {pct}%
          </span>
        </div>
        )}
      </td>
      <td style={{ padding: "8px 10px" }}>
        {field.source?.snippet ? (
          <div
            className="snippet-box"
            style={{
              background: "rgba(0, 0, 0, 0.25)",
              border: "1px solid var(--border-subtle, #334155)",
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 12,
              fontFamily: "var(--font-mono, monospace)",
              color: "#cbd5e1",
              maxWidth: 320,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={field.source.snippet}
          >
            {field.source.page !== undefined && (
              <span style={{ color: "var(--accent-cyan, #06b6d4)", marginRight: 6 }}>
                [p.{field.source.page}]
              </span>
            )}
            “{field.source.snippet}”
          </div>
        ) : (
          <span className="faint" style={{ fontSize: 11 }}>—</span>
        )}
      </td>
    </tr>
  );
}

function formatFieldValue(field: ExtractedField, currency: string): string {
  const v = field.value;
  if (v === null || v === undefined) return "—";
  if (/(amount|total|price|balance)/i.test(field.name)) {
    const minor = /_minor$/.test(field.name)
      ? typeof v === "number" ? v : /^-?\d+$/.test(String(v)) ? Number(v) : null
      : majorAmountToMinor(v);
    if (minor !== null && Number.isSafeInteger(minor)) return formatMoney(minor, currency);
  }
  if (typeof v === "number") return String(v);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = Math.round(bytes / 1024);
  return `${kb} KB`;
}

function humanizeFieldName(name: string): string {
  const labels: Record<string, string> = {
    beneficiary: "Seller", applicant: "Buyer", buyer: "Buyer", seller: "Seller",
    total_amount_minor: "Total amount", amount_minor: "Amount", currency: "Currency",
    goods_description: "Goods", description_of_goods: "Goods", shipment_date: "Shipment date",
    latest_shipment_date: "Latest ship date", expiry_date: "Expiry date", lc_number: "Letter of credit number",
  };
  return labels[name] ?? name.replace(/_minor$/, "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
