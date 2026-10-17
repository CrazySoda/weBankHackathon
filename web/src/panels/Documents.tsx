import { useState } from "react";
import type { DealState, ExtractedField } from "../api";
import { formatMoney, shortHash } from "../api";
import { SyntheticChip, confidenceColor } from "../ui";
import {
  FileText,
  FileSpreadsheet,
  FileCheck,
  FileQuestion,
  Copy,
  Check,
  AlertTriangle,
  Info,
} from "lucide-react";

const KIND_META: Record<string, { label: string; icon: typeof FileText }> = {
  letter_of_credit: { label: "Letter of Credit", icon: FileCheck },
  commercial_invoice: { label: "Commercial Invoice", icon: FileText },
  packing_list: { label: "Packing List", icon: FileSpreadsheet },
  bill_of_lading: { label: "Bill of Lading", icon: FileText },
  unknown: { label: "Unknown document", icon: FileQuestion },
};

export default function Documents({ state }: { state: DealState }) {
  const extracted = state.extracted;
  const unextracted = state.documents.filter(
    (d) => !extracted.some((e) => e.doc_id === d.doc_id),
  );

  if (state.documents.length === 0) {
    return (
      <div className="empty" style={{ padding: 32, textAlign: "center" }}>
        <FileQuestion size={32} style={{ margin: "0 auto 12px", opacity: 0.4 }} />
        <p>No documents uploaded yet.</p>
        <p className="faint" style={{ fontSize: 13 }}>
          Use the sidebar or a demo scenario to load an LC, invoice, or packing list.
        </p>
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
                  <span>low confidence</span>
                </span>
              )}
              <DocHashCopy hash={doc.sha256} />
              <span className="chip" style={{ background: "rgba(255,255,255,0.04)", fontSize: 11 }}>
                {doc.extraction_model}
              </span>
              <SyntheticChip />
            </div>

            {doc.fields.length === 0 ? (
              <div className="empty">No fields extracted from this document.</div>
            ) : (
              <div className="fields-table-wrapper" style={{ overflowX: "auto" }}>
                <table className="fields-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle, #334155)", textAlign: "left", color: "#94a3b8" }}>
                      <th style={{ padding: "8px 10px", width: "24%" }}>Field</th>
                      <th style={{ padding: "8px 10px", width: "28%" }}>Extracted Value</th>
                      <th style={{ padding: "8px 10px", width: "20%" }}>Confidence</th>
                      <th style={{ padding: "8px 10px", width: "28%" }}>Text Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.fields.map((f, i) => (
                      <FieldRow key={i} field={f} />
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
              <DocHashCopy hash={d.sha256} />
              <span className="faint mono" style={{ fontSize: 11 }}>
                {formatFileSize(d.size_bytes)} · {d.mime}
              </span>
            </div>
            <div className="faint" style={{ fontSize: 12 }}>
              Extraction runs automatically as part of the LangGraph deal pipeline — press “Run deal”.
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

function DocHashCopy({ hash }: { hash: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="btn-link mono faint"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        background: "rgba(168, 85, 247, 0.08)",
        color: "var(--accent-violet, #a855f7)",
        border: "1px solid rgba(168, 85, 247, 0.2)",
        borderRadius: 4,
        padding: "2px 6px",
        fontSize: 11,
        cursor: "pointer",
      }}
      onClick={() => {
        void navigator.clipboard.writeText(hash);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      title={`SHA-256: ${hash} (click to copy)`}
    >
      <span>sha256:{shortHash(hash, 10)}</span>
      {copied ? <Check size={11} color="var(--status-pass, #10b981)" /> : <Copy size={11} />}
    </button>
  );
}

function FieldRow({ field }: { field: ExtractedField }) {
  const pct = Math.round(field.confidence * 100);
  const color = confidenceColor(field.confidence);
  const value = formatFieldValue(field);

  return (
    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
      <td style={{ padding: "8px 10px", fontWeight: 500, color: "#e2e8f0" }}>
        <code>{field.name}</code>
      </td>
      <td style={{ padding: "8px 10px", color: "var(--text-main, #f8fafc)" }}>
        {value}
      </td>
      <td style={{ padding: "8px 10px" }}>
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

function formatFieldValue(field: ExtractedField): string {
  const v = field.value;
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    // minor-unit money fields get currency formatting without float division
    if (/(minor|_usd|amount|total|price|balance)/.test(field.name)) {
      return formatMoney(v, field.name.includes("usd") ? "USD" : "USD");
    }
    return String(v);
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = Math.round(bytes / 1024);
  return `${kb} KB`;
}
