import { useState } from "react";
import type { Finding, DealState } from "../api";
import { SeverityChip, StatusChip } from "../ui";
import { getRuleExplanation } from "../config/ruleExplanations";
import {
  FileText,
  Copy,
  Check,
  UploadCloud,
  HelpCircle,
  FileCheck,
  ChevronRight,
  Split,
  SearchCheck,
  ArrowRight,
} from "lucide-react";

interface FindingsProps {
  state: DealState;
  onUploadCorrectedDoc?: (file: File) => void;
  uploadingDoc?: boolean;
  onRunReview?: () => void;
}

export default function Findings({
  state,
  onUploadCorrectedDoc,
  uploadingDoc = false,
  onRunReview,
}: FindingsProps) {
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [copiedDraft, setCopiedDraft] = useState(false);

  const blocks = state.findings.filter((f) => f.severity === "block");
  const warns = state.findings.filter((f) => f.severity === "warn");
  const infos = state.findings.filter((f) => f.severity === "info");

  const copyAmendmentDraft = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedDraft(true);
    setTimeout(() => setCopiedDraft(false), 2000);
  };

  if (state.findings.length === 0) {
    return (
      <div className={`empty-state-panel ${state.check_plan ? "empty-state-success" : ""}`}>
        <div className="empty-state-content">
          <div className="empty-state-icon"><SearchCheck size={25} strokeWidth={1.8} /></div>
          <span className="empty-state-kicker">{state.check_plan ? "Review complete" : "Your next step"}</span>
          <h2 className="empty-state-title">
            {state.check_plan ? "Everything looks clear" : "Check your documents for issues"}
          </h2>
          <p className="empty-state-copy">
            {state.check_plan
              ? "We didn’t find anything that needs your attention. You can review your documents or come back here after an update."
              : "Run a review to check the details in your trade documents and see anything that may need attention."}
          </p>
          {!state.check_plan && onRunReview && (
            <button className="empty-state-button" onClick={onRunReview}>
              Review this deal <ArrowRight size={16} />
            </button>
          )}
          <div className="empty-state-footnote">
            {state.check_plan ? "Your documents were checked against the deal details." : "Usually takes less than a minute"}
          </div>
        </div>
        <div className="empty-state-art" aria-hidden="true">
          <span /><span /><span />
        </div>
      </div>
    );
  }

  return (
    <div className="findings-layout">
      <div className="findings-main-column">
        {/* Amendment Draft Banner if await_corrected_doc is active */}
        {state.amendment_draft && (
          <div
            className="card"
            style={{
              borderColor: "var(--status-warn, #f59e0b)",
              background: "var(--status-warn-dim, #f59e0b11)",
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 14, color: "var(--status-warn, #f59e0b)" }}>
                  Suggested change prepared
                </h3>
                <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--text-dim, #94a3b8)" }}>
                  Share this draft with your buyer, or add an updated invoice below.
                </p>
              </div>
              <button
                onClick={() => copyAmendmentDraft(state.amendment_draft!)}
                className="chip"
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  background: "var(--bg-card, #161e29)",
                  border: "1px solid var(--border-subtle, #232d3b)",
                }}
              >
                {copiedDraft ? <Check size={12} color="var(--status-pass)" /> : <Copy size={12} />}
                  <span>{copiedDraft ? "Copied" : "Copy suggestion"}</span>
              </button>
            </div>
            <pre
              style={{
                background: "var(--bg-base, #0b0f14)",
                padding: "8px 12px",
                borderRadius: "var(--radius-sm, 6px)",
                fontSize: 12,
                fontFamily: "var(--mono)",
                color: "var(--text, #e6ebf2)",
                whiteSpace: "pre-wrap",
                margin: "0 0 12px",
              }}
            >
              {state.amendment_draft}
            </pre>

            {onUploadCorrectedDoc && (
              <div
                style={{
                  border: "1px dashed var(--status-warn, #f59e0b)",
                  borderRadius: "var(--radius-sm, 6px)",
                  padding: "12px",
                  textAlign: "center",
                  background: "var(--bg-card, #161e29)",
                }}
              >
                <input
                  type="file"
                  id="corrected-doc-input"
                  accept="application/pdf,image/jpeg,image/png"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) onUploadCorrectedDoc(file);
                  }}
                  disabled={uploadingDoc}
                />
                <label
                  htmlFor="corrected-doc-input"
                  style={{
                    cursor: uploadingDoc ? "not-allowed" : "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    color: "var(--status-warn, #f59e0b)",
                    fontSize: 13,
                    fontWeight: 600,
                  }}
                >
                  <UploadCloud size={16} />
                  <span>{uploadingDoc ? "Adding updated invoice…" : "Add an updated invoice"}</span>
                </label>
              </div>
            )}
          </div>
        )}

        {/* Severity Groups: Block -> Warn -> Info */}
        {blocks.length > 0 && (
          <div className="severity-group">
            <h3 className="severity-title" style={{ color: "var(--status-block, #f43f5e)" }}>
              Needs to be fixed ({blocks.length})
            </h3>
            {blocks.map((f) => (
              <FindingCard
                key={`${f.check_id}:${f.rule_id}`}
                finding={f}
                isSelected={selectedFinding?.rule_id === f.rule_id}
                onSelect={() => setSelectedFinding(f)}
              />
            ))}
          </div>
        )}

        {warns.length > 0 && (
          <div className="severity-group">
            <h3 className="severity-title" style={{ color: "var(--status-warn, #f59e0b)" }}>
              Worth a review ({warns.length})
            </h3>
            {warns.map((f) => (
              <FindingCard
                key={`${f.check_id}:${f.rule_id}`}
                finding={f}
                isSelected={selectedFinding?.rule_id === f.rule_id}
                onSelect={() => setSelectedFinding(f)}
              />
            ))}
          </div>
        )}

        {infos.length > 0 && (
          <div className="severity-group">
            <h3 className="severity-title" style={{ color: "var(--status-info, #94a3b8)" }}>
              Other notes ({infos.length})
            </h3>
            {infos.map((f) => (
              <FindingCard
                key={`${f.check_id}:${f.rule_id}`}
                finding={f}
                isSelected={selectedFinding?.rule_id === f.rule_id}
                onSelect={() => setSelectedFinding(f)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Split-Screen Evidence Inspector Drawer/Panel */}
      {selectedFinding && (
        <div className="evidence-inspector-sidebar">
          <div className="card" style={{ height: "100%", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Split size={16} color="var(--border-focus, #06b6d4)" />
                <h3 style={{ margin: 0, fontSize: 14 }}>Why this was flagged</h3>
              </div>
              <button
                onClick={() => setSelectedFinding(null)}
                style={{ background: "transparent", border: "none", color: "var(--text-dim)", cursor: "pointer", fontSize: 16 }}
              >
                ✕
              </button>
            </div>

            <div style={{ marginBottom: 12 }}>
              <SeverityChip severity={selectedFinding.severity} />
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 6 }}>{selectedFinding.summary}</div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {selectedFinding.evidence.length === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>No highlighted document snippet attached.</p>
              ) : (
                selectedFinding.evidence.map((e, idx) => {
                  const doc = state.documents.find((d) => d.doc_id === e.doc_id);
                  return (
                    <div
                      key={idx}
                      style={{
                        background: "var(--bg-base, #0b0f14)",
                        border: "1px solid var(--border-subtle, #232d3b)",
                        borderRadius: "var(--radius-sm, 6px)",
                        padding: 10,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 11,
                          color: "var(--text-dim, #94a3b8)",
                          marginBottom: 6,
                        }}
                      >
                        <FileText size={12} />
                        <span>{doc?.filename || e.doc_id}</span>
                        {e.source.page !== null && e.source.page !== undefined && <span>· Page {e.source.page}</span>}
                      </div>

                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 12,
                          background: "var(--bg-card, #161e29)",
                          borderLeft: "3px solid var(--border-focus, #06b6d4)",
                          padding: "6px 8px",
                          color: "var(--text, #e6ebf2)",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {e.quote || e.source.snippet || "(No quote available)"}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FindingCard({
  finding,
  isSelected,
  onSelect,
}: {
  finding: Finding;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const explanation = getRuleExplanation(finding.rule_id, finding.summary, finding.explanation);

  return (
    <div
      className={`finding sev-${finding.severity} ${isSelected ? "selected-finding" : ""}`}
      style={{
        cursor: "pointer",
        transition: "border-color 0.15s ease",
        borderColor: isSelected ? "var(--border-focus, #06b6d4)" : undefined,
      }}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect();
      }}
    >
      <div className="finding-head">
        <SeverityChip severity={finding.severity} />
        <StatusChip status={finding.status} />
        <span className="finding-rule">{explanation.ruleReference}</span>
        {finding.fixable && (
          <span className="chip chip-sev-info" title="Fixable via corrected document upload">
            fixable
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="faint mono" style={{ fontSize: 11 }}>
          </span>
          <ChevronRight size={14} color="var(--text-faint, #64748b)" />
        </div>
      </div>

      <div className="finding-summary" style={{ fontSize: 14, fontWeight: 700, margin: "6px 0 4px" }}>
        {explanation.title}
      </div>

      {/* "What this means" (Plain language sentence) */}
      <div style={{ fontSize: 13, color: "var(--text, #e6ebf2)", marginBottom: 6 }}>
        <strong>What this means:</strong> {explanation.whatThisMeans}
      </div>

      {/* "What to do next" */}
      <div style={{ fontSize: 12, color: "var(--text-dim, #94a3b8)", marginBottom: 8 }}>
        <strong>What to do next:</strong> {explanation.whatToDoNext}
      </div>

      {/* Jargon Tooltip Box */}
      {explanation.jargonTooltip && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: 11,
            color: "var(--text-faint, #64748b)",
            background: "var(--bg-base, #0b0f14)",
            padding: "3px 8px",
            borderRadius: 4,
          }}
          title={explanation.jargonTooltip}
        >
          <HelpCircle size={12} />
          <span>Rule Rationale: {explanation.jargonTooltip}</span>
        </div>
      )}

      {finding.evidence.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 11, color: "var(--border-focus, #06b6d4)", display: "flex", alignItems: "center", gap: 4 }}>
          <FileCheck size={12} />
          <span>View the supporting document details</span>
        </div>
      )}
    </div>
  );
}
