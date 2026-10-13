import type { DealState, ExtractedField } from "../api";
import { formatMoney, shortHash } from "../api";
import { SyntheticChip, confidenceColor } from "../ui";

const KIND_LABELS: Record<string, string> = {
  letter_of_credit: "Letter of Credit",
  commercial_invoice: "Commercial Invoice",
  packing_list: "Packing List",
  bill_of_lading: "Bill of Lading",
  unknown: "Unknown document",
};

export default function Documents({ state }: { state: DealState }) {
  const extracted = state.extracted;
  const unextracted = state.documents.filter(
    (d) => !extracted.some((e) => e.doc_id === d.doc_id),
  );

  if (state.documents.length === 0) {
    return <div className="empty">No documents uploaded. Use the sidebar to add LC, invoice, packing list or bill of lading.</div>;
  }

  return (
    <div>
      {extracted.map((doc) => (
        <div className="doc-block" key={doc.doc_id}>
          <div className="doc-head">
            <span className="doc-filename">{filenameFor(state, doc.doc_id)}</span>
            <span className="chip chip-sev-info">{KIND_LABELS[doc.kind] ?? doc.kind}</span>
            {doc.low_confidence && (
              <span className="chip chip-sev-warn">low confidence</span>
            )}
            <span className="faint mono" style={{ fontSize: 11 }}>
              sha256 {shortHash(doc.sha256, 14)} · {doc.extraction_model}
            </span>
            <SyntheticChip />
          </div>
          {doc.fields.length === 0 ? (
            <div className="empty">No fields extracted.</div>
          ) : (
            doc.fields.map((f, i) => <FieldRow key={i} field={f} />)
          )}
        </div>
      ))}

      {unextracted.map((d) => (
        <div className="doc-block" key={d.doc_id}>
          <div className="doc-head">
            <span className="doc-filename">{d.filename}</span>
            <span className="chip chip-sev-info">{KIND_LABELS[d.kind] ?? d.kind}</span>
            <span className="chip chip-status-open">not extracted</span>
            <span className="faint mono" style={{ fontSize: 11 }}>
              sha256 {shortHash(d.sha256, 14)} · {(d.size_bytes / 1024).toFixed(1)} KB · {d.mime}
            </span>
          </div>
          <div className="faint" style={{ fontSize: 12 }}>
            Extraction runs as part of the deal graph — press “Run deal”.
          </div>
        </div>
      ))}
    </div>
  );
}

function filenameFor(state: DealState, docId: string): string {
  return state.documents.find((d) => d.doc_id === docId)?.filename ?? docId;
}

function FieldRow({ field }: { field: ExtractedField }) {
  const pct = Math.round(field.confidence * 100);
  const value = formatFieldValue(field);
  return (
    <>
      <div className="field-row">
        <div className="field-name">{field.name}</div>
        <div className="field-value">{value}</div>
        <div className="confidence">
          <div className="bar">
            <div
              className="fill"
              style={{ width: `${pct}%`, background: confidenceColor(field.confidence) }}
            />
          </div>
          <span className="pct">{pct}%</span>
        </div>
        {field.source.snippet && <div className="snippet">“{field.source.snippet}”</div>}
      </div>
    </>
  );
}

function formatFieldValue(field: ExtractedField): string {
  const v = field.value;
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    // minor-unit money fields get currency formatting; other numbers stay raw
    if (/(minor|_usd|amount|total|price|balance)/.test(field.name)) {
      return formatMoney(v, field.name.includes("usd") ? "USD" : "USD");
    }
    return String(v);
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
