import { useState, useRef } from "react";
import type { DocKind } from "../api";
import {
  FileUp,
  X,
  FileCheck,
  FileText,
  FileSpreadsheet,
  Check,
  AlertCircle,
  Loader2,
} from "lucide-react";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File, kind: DocKind) => Promise<void>;
  isUploading: boolean;
}

const KINDS: Array<{ id: DocKind; label: string; desc: string; icon: typeof FileText }> = [
  {
    id: "letter_of_credit",
    label: "Letter of Credit",
    desc: "Governing financial instrument (MT700 / credit agreement)",
    icon: FileCheck,
  },
  {
    id: "commercial_invoice",
    label: "Commercial Invoice",
    desc: "Itemized billing document with total amounts and currency",
    icon: FileText,
  },
  {
    id: "packing_list",
    label: "Packing List",
    desc: "Physical weights, package counts, and carton dimensions",
    icon: FileSpreadsheet,
  },
  {
    id: "bill_of_lading",
    label: "Bill of Lading",
    desc: "Carrier transport title, port of loading, vessel name",
    icon: FileText,
  },
];

export default function UploadModal({
  isOpen,
  onClose,
  onUpload,
  isUploading,
}: UploadModalProps) {
  const [selectedKind, setSelectedKind] = useState<DocKind>("commercial_invoice");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setError(null);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      validateAndSet(file);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (e.target.files && e.target.files[0]) {
      validateAndSet(e.target.files[0]);
    }
  };

  const validateAndSet = (file: File) => {
    const validExts = [".pdf", ".jpg", ".jpeg", ".png"];
    const hasValidExt = validExts.some((ext) => file.name.toLowerCase().endsWith(ext));
    if (!hasValidExt) {
      setError("Please select a PDF or image file (.pdf, .jpg, .png).");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("File exceeds maximum allowed size (10 MB).");
      return;
    }
    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile) {
      setError("Please select a document file to upload.");
      return;
    }
    try {
      setError(null);
      await onUpload(selectedFile, selectedKind);
      setSelectedFile(null);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload document");
    }
  };

  return (
    <div
      className="modal-overlay"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(5px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isUploading) onClose();
      }}
    >
      <div
        className="modal-card"
        style={{
          background: "var(--bg-card, #161e29)",
          border: "1px solid var(--border-subtle, #334155)",
          borderRadius: "var(--radius, 10px)",
          maxWidth: 540,
          width: "100%",
          padding: 24,
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: "50%",
                background: "rgba(6, 182, 212, 0.12)",
                color: "var(--accent-cyan, #06b6d4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <FileUp size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
                Upload Trade Document
              </h3>
              <p style={{ margin: 0, fontSize: 12, color: "var(--text-dim, #94a3b8)" }}>
                Attach document into the active trade finance deal
              </p>
            </div>
          </div>
          <button
            className="btn-link"
            onClick={onClose}
            disabled={isUploading}
            style={{ color: "var(--text-dim, #94a3b8)", cursor: "pointer", background: "none", border: "none" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Step 1: Select Document Kind */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-dim, #94a3b8)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            1. Document Classification
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {KINDS.map((k) => {
              const Icon = k.icon;
              const isSelected = selectedKind === k.id;
              return (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => setSelectedKind(k.id)}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    padding: "8px 10px",
                    borderRadius: "var(--radius-sm, 6px)",
                    border: isSelected
                      ? "1px solid var(--accent-cyan, #06b6d4)"
                      : "1px solid var(--border-subtle, #334155)",
                    background: isSelected
                      ? "rgba(6, 182, 212, 0.1)"
                      : "rgba(0, 0, 0, 0.2)",
                    color: isSelected ? "var(--accent-cyan, #06b6d4)" : "var(--text, #e2e8f0)",
                    textAlign: "left",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <Icon size={16} style={{ marginTop: 2, flexShrink: 0 }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{k.label}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Step 2: Drag and Drop Upload Zone */}
        <div style={{ marginBottom: 18 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-dim, #94a3b8)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            2. Choose File (.PDF, .PNG, .JPG)
          </label>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: dragOver
                ? "2px dashed var(--accent-cyan, #06b6d4)"
                : selectedFile
                  ? "1px solid rgba(16, 185, 129, 0.4)"
                  : "2px dashed var(--border-subtle, #334155)",
              background: dragOver
                ? "rgba(6, 182, 212, 0.08)"
                : selectedFile
                  ? "rgba(16, 185, 129, 0.06)"
                  : "rgba(0, 0, 0, 0.25)",
              borderRadius: "var(--radius-sm, 6px)",
              padding: 24,
              textAlign: "center",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            {selectedFile ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
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
                  }}
                >
                  <Check size={18} />
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                  {selectedFile.name}
                </div>
                <div className="mono faint" style={{ fontSize: 11 }}>
                  {formatBytes(selectedFile.size)} · Click to change file
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <FileUp size={24} style={{ color: "var(--text-dim, #94a3b8)", opacity: 0.6 }} />
                <div style={{ fontSize: 13, color: "var(--text, #e2e8f0)", fontWeight: 500 }}>
                  Drag & drop file here, or <span style={{ color: "var(--accent-cyan, #06b6d4)" }}>browse</span>
                </div>
                <div className="faint" style={{ fontSize: 11 }}>
                  PDF, JPG, or PNG up to 10 MB
                </div>
              </div>
            )}
          </div>
        </div>

        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 12px",
              background: "rgba(244, 63, 94, 0.1)",
              border: "1px solid rgba(244, 63, 94, 0.3)",
              borderRadius: 6,
              color: "var(--status-block, #f43f5e)",
              fontSize: 12,
              marginBottom: 16,
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Footer Actions */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isUploading}
          >
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={isUploading || !selectedFile}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            {isUploading ? (
              <>
                <Loader2 size={14} className="spinner" />
                <span>Uploading Document…</span>
              </>
            ) : (
              <>
                <FileUp size={14} />
                <span>Upload & Register</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = Math.round(bytes / 1024);
  if (kb < 1024) return `${kb} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}
