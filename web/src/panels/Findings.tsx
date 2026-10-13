import type { Finding, DealState } from "../api";
import { SeverityChip, StatusChip } from "../ui";

const ORDER: Record<string, number> = { block: 0, warn: 1, info: 2 };

export default function Findings({ state }: { state: DealState }) {
  const sorted = [...state.findings].sort(
    (a, b) =>
      (ORDER[a.severity] ?? 3) - (ORDER[b.severity] ?? 3) ||
      a.check_id.localeCompare(b.check_id),
  );

  if (sorted.length === 0) {
    return (
      <div className="empty">
        No findings{state.check_plan ? "" : " — run the deal to execute compliance checks"}.
      </div>
    );
  }

  return (
    <div>
      {sorted.map((f) => (
        <FindingCard key={`${f.check_id}:${f.rule_id}`} finding={f} state={state} />
      ))}
    </div>
  );
}

function FindingCard({ finding, state }: { finding: Finding; state: DealState }) {
  const docName = (docId: string) =>
    state.documents.find((d) => d.doc_id === docId)?.filename ?? docId;

  return (
    <div className={`finding sev-${finding.severity}`}>
      <div className="finding-head">
        <SeverityChip severity={finding.severity} />
        <StatusChip status={finding.status} />
        <span className="finding-rule">{finding.rule_id}</span>
        {finding.fixable && (
          <span className="chip chip-sev-info" title="resolve_exception can draft an amendment">
            fixable
          </span>
        )}
        <span className="faint mono" style={{ fontSize: 11, marginLeft: "auto" }}>
          {finding.check_id}
        </span>
      </div>
      <div className="finding-summary">{finding.summary}</div>
      {finding.explanation && <div className="finding-explanation">{finding.explanation}</div>}
      {finding.evidence.map((e, i) => (
        <div key={i} className="evidence">
          <div className="quote">{e.quote || e.source.snippet || "(no quoted text)"}</div>
          <div className="evidence-meta">
            {docName(e.doc_id)}
            {e.source.page !== null && e.source.page !== undefined ? ` · page ${e.source.page}` : ""}
            {e.source.text_span ? ` · chars ${e.source.text_span[0]}–${e.source.text_span[1]}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
