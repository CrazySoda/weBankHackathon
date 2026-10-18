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

export default function UploadModal({ isOpen, onClose, onUpload, onRemoveDocument, removingDocId, isUploading, state, onCheckReadiness, isChecking, isRunning }: UploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<DocKind>("letter_of_credit");
  const [file, setFile] = useState<File | null>(null);
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
    setFile(null);
    setAddedNotice("");
    onClose();
  };

  const chooseFile = (candidate?: File) => {
    setError(null);
    if (!candidate) return;
    const allowed = /\.(pdf|jpe?g|png)$/i.test(candidate.name);
    if (!allowed) return setError("Choose a PDF, JPG, or PNG file.");
    if (candidate.size > 10 * 1024 * 1024) return setError("Files must be smaller than 10 MB.");
    setFile(candidate);
  };

  const submit = async () => {
    if (!file) return setError("Choose a file to continue.");
    setError(null);
    try {
      await onUpload(file, kind);
      setAddedNotice(`${file.name} added. Add another file or check readiness.`);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The file could not be uploaded.");
    }
  };

  return <div className="modal-overlay upload-overlay" onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
    <section className="upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <header className="upload-modal-head">
        <div className="upload-modal-icon"><ArrowUpFromLine size={19}/></div>
        <div><h2 id="upload-title">Trade documents</h2><p>Add files one by one. Your documents stay visible here.</p></div>
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
            <div className="upload-add-card-head"><span className="upload-add-icon"><ArrowUpFromLine size={16}/></span><span><strong>{file ? "Ready to add" : "Add a document"}</strong><small>PDF, JPG, or PNG · under 10 MB</small></span></div>
            <label className="upload-label" htmlFor="document-kind">Document type</label>
            <select id="document-kind" className="upload-kind-select" value={kind} onChange={(event) => setKind(event.target.value as DocKind)}>
              {TYPES.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
            </select>
            <input ref={inputRef} className="visually-hidden" type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(event) => chooseFile(event.target.files?.[0])}/>
            <button className={`upload-dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`} type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]); }}>
              <span className="upload-drop-icon">{file ? <FileText size={19}/> : <Image size={19}/>}</span>
              {file ? <><strong>{file.name}</strong><span>{formatBytes(file.size)} · Click to change</span></> : <><strong>Drop a file here</strong><span>or <em>browse files</em></span></>}
            </button>
            {file && <button className="btn btn-primary upload-add-button" onClick={() => void submit()} disabled={isUploading}>{isUploading ? <Loader2 size={15} className="spinner"/> : <ArrowUpFromLine size={15}/>} {isUploading ? "Adding…" : "Add document"}</button>}
          </section>
        </div>

        {addedNotice && <div className="upload-added-notice"><Check size={14}/>{addedNotice}</div>}
        <div className="upload-modal-footnote">AI checks key details, not whether a document is correct.<UploadTooltip label="How AI document checking works" content="AI extracts document details, then a fixed checklist checks whether key information was found. The full review checks deal issues. This is not a certification that documents are correct. PDF text is extracted; images can be stored but are not text-extracted yet."><HelpCircle size={13}/></UploadTooltip><UploadTooltip label="Combined PDF details" content="You can upload a combined PDF as Other / combined PDF, but this review reads one document type per file. Split a combined PDF into the letter of credit, invoice, and packing list for a more complete review."><FileText size={13}/></UploadTooltip></div>
        {error && <div className="upload-error" role="alert"><AlertCircle size={15}/>{error}</div>}
      </div>
      <footer className="upload-modal-foot">
        <button className="btn btn-secondary" onClick={close} disabled={isUploading}>Done</button>
        <div className="upload-modal-actions">
          <button className="btn btn-secondary" onClick={() => void onCheckReadiness()} disabled={!state?.documents.length || isUploading || isRunning || isChecking || Boolean(file)} title="Extract documents and check required details without starting the full deal review">{isChecking ? <Loader2 size={15} className="spinner"/> : <Sparkles size={15}/>} {isChecking ? "Checking…" : "Check readiness"}</button>
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
