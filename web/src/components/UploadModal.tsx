import { useEffect, useRef, useState } from "react";
import type { DealState, DocKind } from "../api";
import { AlertCircle, ArrowUpFromLine, Check, Clock3, FileText, HelpCircle, Image, Loader2, PackageCheck, Sparkles, Trash2, X } from "lucide-react";
import { documentReadiness } from "../documentReadiness";
import { UploadTooltip } from "./UploadTooltip";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File, kind: DocKind) => Promise<void>;
  onRemoveDocument: (docId: string) => Promise<void>;
  removingDocId: string | null;
  isUploading: boolean;
  state: DealState | null;
  onCheckReadiness: () => Promise<void>;
  isChecking: boolean;
  isRunning: boolean;
}

const TYPES: Array<{ id: DocKind; label: string }> = [
  { id: "letter_of_credit", label: "Letter of credit" },
  { id: "commercial_invoice", label: "Commercial invoice" },
  { id: "packing_list", label: "Packing list" },
  { id: "bill_of_lading", label: "Bill of lading" },
  { id: "presentation_schedule", label: "Presentation schedule" },
  { id: "unknown", label: "Other / combined PDF" },
];

interface StagedFile {
  id: string;
  file: File;
  kind: DocKind;
}

function detectDocKind(filename: string): DocKind {
  const lower = filename.toLowerCase();
  if (lower.includes("lc") || lower.includes("credit") || lower.includes("mt700") || lower.includes("lca")) {
    return "letter_of_credit";
  }
  if (lower.includes("inv") || lower.includes("invoice") || lower.includes("bill_of_sale")) {
    return "commercial_invoice";
  }
  if (lower.includes("pl") || lower.includes("pack") || lower.includes("packing")) {
    return "packing_list";
  }
  if (lower.includes("bl") || lower.includes("lading") || lower.includes("bol") || lower.includes("ocean") || lower.includes("waybill")) {
    return "bill_of_lading";
  }
  if (lower.includes("sched") || lower.includes("presentation")) {
    return "presentation_schedule";
  }
  return "unknown";
}

export default function UploadModal({ isOpen, onClose, onUpload, onRemoveDocument, removingDocId, isUploading, state, onCheckReadiness, isChecking, isRunning }: UploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<DocKind>("letter_of_credit");
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [uploadProgress, setUploadProgress] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addedNotice, setAddedNotice] = useState("");
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const checklist = documentReadiness(state);
  const documents = state?.documents ?? [];
  const uploadedCount = checklist.filter((item) => item.uploaded).length;
  const checkedCount = checklist.filter((item) => item.status === "ready" || item.status === "review").length;
  const attentionCount = checklist.filter((item) => item.status === "review").length;
  const canRemoveDocuments = Boolean(state && !state.check_plan && state.findings.length === 0 && state.fx_options.length === 0 && !state.cash_projection && !state.finance_offer && !state.policy && !state.approval && !state.receipt && !state.report_summary && !state.fatal_error && !state.escalation_reason && !state.pending_doc);
  const unclassifiedCount = state?.documents.filter((doc) =>
    doc.kind === "unknown" && !state.extracted.some((extracted) => extracted.doc_id === doc.doc_id),
  ).length ?? 0;

  useEffect(() => {
    if (isOpen) setKind(checklist.find((item) => !item.uploaded)?.requirement.kind ?? "unknown");
  }, [isOpen, state]);

  if (!isOpen) return null;

  const close = () => {
    if (isUploading) return;
    setError(null);
    setStagedFiles([]);
    setUploadProgress("");
    setAddedNotice("");
    onClose();
  };

  const addFiles = (candidates: File[]) => {
    setError(null);
    if (!candidates.length) return;
    const newItems: StagedFile[] = [];
    for (const candidate of candidates) {
      const allowed = /\.(pdf|jpe?g|png)$/i.test(candidate.name);
      if (!allowed) {
        setError("One or more files skipped: must be a PDF, JPG, or PNG file.");
        continue;
      }
      if (candidate.size > 10 * 1024 * 1024) {
        setError(`File ${candidate.name} skipped: exceeds 10 MB limit.`);
        continue;
      }
      // If single file and user explicitly selected a kind other than default, prioritize kind; otherwise auto-detect
      const detected = candidates.length === 1 && kind !== "unknown" ? kind : detectDocKind(candidate.name);
      newItems.push({
        id: Math.random().toString(36).substring(2, 9),
        file: candidate,
        kind: detected,
      });
    }
    if (newItems.length > 0) {
      setStagedFiles((prev) => [...prev, ...newItems]);
    }
  };

  const removeStagedFile = (id: string) => {
    setStagedFiles((prev) => prev.filter((item) => item.id !== id));
  };

  const updateStagedKind = (id: string, newKind: DocKind) => {
    setStagedFiles((prev) =>
      prev.map((item) => (item.id === id ? { ...item, kind: newKind } : item))
    );
  };

  const submitBatch = async () => {
    if (!stagedFiles.length) return setError("Choose or drop one or more files to continue.");
    setError(null);
    try {
      for (let i = 0; i < stagedFiles.length; i++) {
        const item = stagedFiles[i];
        setUploadProgress(`Adding ${i + 1} of ${stagedFiles.length}: ${item.file.name}…`);
        await onUpload(item.file, item.kind);
      }
      setAddedNotice(
        stagedFiles.length === 1
          ? `${stagedFiles[0].file.name} added. Add more files or check readiness.`
          : `${stagedFiles.length} documents added successfully. Check readiness or add more.`
      );
      setStagedFiles([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The files could not be uploaded.");
    } finally {
      setUploadProgress("");
    }
  };

  return <div className="modal-overlay upload-overlay" onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
    <section className="upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <header className="upload-modal-head">
        <div className="upload-modal-icon"><ArrowUpFromLine size={19}/></div>
        <div>
          <h2 id="upload-title">Trade documents</h2>
          <p>Drop single or multiple files at once. Document types are auto-classified.</p>
        </div>
        <button className="icon-button" onClick={close} disabled={isUploading} aria-label="Close"><X size={19}/></button>
      </header>
      <div className="upload-modal-content">
        <section className="upload-checklist upload-readiness-summary" aria-label="Recommended core documents">
          <div className="upload-checklist-head">
            <div><span className="upload-checklist-kicker">Core document set</span><strong>{uploadedCount} of 3 added{unclassifiedCount ? ` · ${unclassifiedCount} unclassified` : ""}</strong><small className="upload-ai-summary">{checkedCount ? `AI checked ${checkedCount}/3 · ${attentionCount ? `${attentionCount} need attention` : "key details found"}` : "Run an AI check after adding files"}</small></div>
            <UploadTooltip label="Why these documents?" content="A letter of credit, commercial invoice, and packing list provide the main deal details. Other documents may be needed depending on the shipment and LC terms."><PackageCheck size={18} aria-hidden="true"/><HelpCircle size={12}/></UploadTooltip>
          </div>
          <div className="upload-checklist-items upload-checklist-compact">
            {checklist.map(({ requirement, status, message }) => {
              const StatusIcon = status === "ready" ? Check : status === "review" ? AlertCircle : status === "uploaded" ? Clock3 : FileText;
              return <div className={`upload-checklist-item ${status}`} key={requirement.kind}>
                <span className="upload-checklist-status"><StatusIcon size={14}/></span>
                <span className="upload-checklist-label"><strong>{requirement.label}</strong></span>
                <span className="upload-checklist-message">{message}</span>
                <UploadTooltip className="upload-detail-help" label={`Details checked for ${requirement.label}`} content={requirement.details}><HelpCircle size={13}/></UploadTooltip>
              </div>;
            })}
          </div>
        </section>

        {documents.length > 0 && <div className="upload-workspace-head"><strong>Your files</strong><span>{documents.length} uploaded</span></div>}
        <div className={`upload-workspace ${documents.length ? "has-documents" : "first-upload"}`}>
          {documents.length > 0 && <div className="upload-file-list" aria-label="Uploaded documents">
            {documents.map((doc) => {
              const typeLabel = TYPES.find((type) => type.id === doc.kind)?.label ?? "Other document";
              const extraction = state?.extracted.find((item) => item.doc_id === doc.doc_id && item.sha256 === doc.sha256);
              const fileStatus = !extraction ? "Check pending" : extraction.fields.length === 0 ? "No details found" : extraction.low_confidence ? "Check details" : "AI checked";
              const fileStatusKind = !extraction || extraction.fields.length === 0 ? "pending" : extraction.low_confidence ? "review" : "checked";
              return <article className="upload-file-card" key={doc.doc_id}>
                <span className="upload-file-icon"><FileText size={17}/></span>
                <span className="upload-file-info"><strong title={doc.filename}>{doc.filename}</strong><small>{typeLabel} · {formatFileType(doc.filename)}</small></span>
                <button className="upload-remove-button" type="button" disabled={!canRemoveDocuments || removingDocId === doc.doc_id} onClick={() => setConfirmRemoveId(doc.doc_id)} aria-label={`Remove ${doc.filename}`} title={canRemoveDocuments ? "Remove from this deal" : "Files are locked after the review starts"}>{removingDocId === doc.doc_id ? <Loader2 size={15} className="spinner"/> : <Trash2 size={15}/>}</button>
                <span className={`upload-file-status ${fileStatusKind}`}>{fileStatus}</span>
                {confirmRemoveId === doc.doc_id && <div className="upload-remove-confirm"><span>Remove this file from the deal?</span><button type="button" onClick={() => setConfirmRemoveId(null)} disabled={Boolean(removingDocId)}>Cancel</button><button type="button" className="confirm-remove" onClick={async () => { try { await onRemoveDocument(doc.doc_id); } catch { setError("The document could not be removed."); } finally { setConfirmRemoveId(null); } }} disabled={Boolean(removingDocId)}>Remove</button></div>}
              </article>;
            })}
          </div>}

          <section className={`upload-add-card ${documents.length === 0 ? "empty" : ""}`} aria-label="Add a document">
            <div className="upload-add-card-head">
              <span className="upload-add-icon"><ArrowUpFromLine size={16}/></span>
              <span>
                <strong>{stagedFiles.length ? `${stagedFiles.length} file${stagedFiles.length > 1 ? "s" : ""} staged` : "Batch drop box"}</strong>
                <small>Drop one or multiple files (.pdf, .jpg, .png)</small>
              </span>
            </div>

            <input
              ref={inputRef}
              className="visually-hidden"
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(event) => {
                if (event.target.files) {
                  addFiles(Array.from(event.target.files));
                }
              }}
            />

            {/* Drag & drop box */}
            <button
              className={`upload-dropzone ${dragging ? "dragging" : ""} ${stagedFiles.length ? "has-file" : ""}`}
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (event.dataTransfer.files) {
                  addFiles(Array.from(event.dataTransfer.files));
                }
              }}
              style={{ minHeight: stagedFiles.length ? 90 : 140 }}
            >
              <span className="upload-drop-icon">{stagedFiles.length ? <FileText size={19}/> : <Image size={19}/>}</span>
              <strong>{stagedFiles.length ? "Click or drop more files to add to batch" : "Drop files here (single or multiple)"}</strong>
              <span>or <em>browse files</em></span>
            </button>

            {/* Staged files queue */}
            {stagedFiles.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, margin: "6px 0 10px", maxHeight: 180, overflowY: "auto" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", display: "flex", justifyContent: "space-between" }}>
                  <span>Staged ({stagedFiles.length}):</span>
                  <button
                    type="button"
                    className="btn-link"
                    style={{ fontSize: 10, color: "var(--text-faint)", background: "none", border: "none", cursor: "pointer" }}
                    onClick={() => setStagedFiles([])}
                  >
                    Clear all
                  </button>
                </div>
                {stagedFiles.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "6px 10px",
                      background: "rgba(0,0,0,0.25)",
                      border: "1px solid #2c3e32",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column" }}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#e4ede6", fontWeight: 500 }} title={item.file.name}>
                        {item.file.name}
                      </span>
                      <span style={{ fontSize: 10, color: "#8c9b91" }}>
                        {formatBytes(item.file.size)}
                      </span>
                    </div>

                    <select
                      className="upload-kind-select"
                      style={{ height: 30, fontSize: 11, padding: "0 6px", width: "auto", minWidth: 140 }}
                      value={item.kind}
                      onChange={(e) => updateStagedKind(item.id, e.target.value as DocKind)}
                      title="Document type"
                    >
                      {TYPES.map((type) => (
                        <option key={type.id} value={type.id}>{type.label}</option>
                      ))}
                    </select>

                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => removeStagedFile(item.id)}
                      title="Remove file from staging"
                      style={{ padding: 4, background: "none", border: "none", color: "#8c9b91", cursor: "pointer" }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {stagedFiles.length > 0 && (
              <button
                className="btn btn-primary upload-add-button"
                onClick={() => void submitBatch()}
                disabled={isUploading}
                style={{ width: "100%", justifyContent: "center" }}
              >
                {isUploading ? <Loader2 size={15} className="spinner"/> : <ArrowUpFromLine size={15}/>}
                {isUploading ? (uploadProgress || "Uploading…") : stagedFiles.length === 1 ? "Add 1 document" : `Upload all ${stagedFiles.length} documents`}
              </button>
            )}
          </section>
        </div>

        {addedNotice && <div className="upload-added-notice"><Check size={14}/>{addedNotice}</div>}
        <div className="upload-modal-footnote">AI checks key details, not whether a document is correct.<UploadTooltip label="How AI document checking works" content="AI extracts document details, then a fixed checklist checks whether key information was found. The full review checks deal issues. This is not a certification that documents are correct. PDF text is extracted. Images and scans are read by a vision model when one is set up, and always need a person to review them."><HelpCircle size={13}/></UploadTooltip><UploadTooltip label="Combined PDF details" content="You can upload a combined PDF as Other / combined PDF, but this review reads one document type per file. Split a combined PDF into the letter of credit, invoice, and packing list for a more complete review."><FileText size={13}/></UploadTooltip></div>
        {error && <div className="upload-error" role="alert"><AlertCircle size={15}/>{error}</div>}
      </div>
      <footer className="upload-modal-foot">
        <button className="btn btn-secondary" onClick={close} disabled={isUploading}>Done</button>
        <div className="upload-modal-actions">
          <button className="btn btn-secondary" onClick={() => void onCheckReadiness()} disabled={!state?.documents.length || isUploading || isRunning || isChecking || stagedFiles.length > 0} title="Extract documents and check required details without starting the full deal review">{isChecking ? <Loader2 size={15} className="spinner"/> : <Sparkles size={15}/>} {isChecking ? "Checking…" : "Check readiness"}</button>
        </div>
      </footer>
    </section>
  </div>;
}

function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatFileType(filename: string): string {
  return filename.split(".").pop()?.toUpperCase() ?? "FILE";
}
