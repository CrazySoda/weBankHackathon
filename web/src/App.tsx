import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DocKind, StreamEvent } from "./api";
import { api } from "./api";
import ApprovalBar from "./components/ApprovalBar";
import PipelineVisualizer from "./components/PipelineVisualizer";
import DemoScenarioLoader from "./components/DemoScenarioLoader";
import UploadModal from "./components/UploadModal";
import { BrandLogo } from "./components/BrandLogo";
import { LoadingSkeleton, ErrorState } from "./components/StateViews";
import Overview from "./panels/Overview";
import Findings from "./panels/Findings";
import Fx from "./panels/Fx";
import CashFlow from "./panels/CashFlow";
import Documents from "./panels/Documents";
import Audit from "./panels/Audit";
import Copilot, { clearCopilotHistory } from "./components/Copilot";
import { useConfirm } from "./components/ConfirmDialog";
import { toast } from "sonner";
import {
  FlaskConical,
  Play,
  Loader2,
  CheckCircle2,
  AlertOctagon,
  Plus,
  FileUp,
  Copy,
  Check,
  Lock,
  Trash2,
  MessageCircle,
  Sparkles,
  ArrowRight,
  Search,
  CircleCheck,
  CircleAlert,
  Clock3,
  FileText,
} from "lucide-react";
import { documentReadiness } from "./documentReadiness";

const DEALS_KEY = "cleartrade.deals";

type TabId = "overview" | "findings" | "fx" | "cash" | "documents" | "audit";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Summary" },
  { id: "findings", label: "Issues" },
  { id: "fx", label: "FX" },
  { id: "cash", label: "Cash flow" },
  { id: "documents", label: "Documents" },
  { id: "audit", label: "Audit" },
];

interface InterruptState {
  payload: Record<string, unknown> | null;
  node: string;
}

function loadDeals(): string[] {
  try {
    const raw = localStorage.getItem(DEALS_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

export default function App() {
  const queryClient = useQueryClient();
  const [confirm, confirmDialog] = useConfirm();
  const [deals, setDeals] = useState<string[]>(loadDeals);
  const [selected, setSelected] = useState<string | null>(() => loadDeals()[0] ?? null);
  const [tab, setTab] = useState<TabId>("overview");
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [dealSearch, setDealSearch] = useState("");

  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [interrupt, setInterrupt] = useState<InterruptState | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    localStorage.setItem(DEALS_KEY, JSON.stringify(deals));
  }, [deals]);

  const dealQuery = useQuery({
    queryKey: ["deal", selected],
    queryFn: () => api.getDeal(selected!),
    enabled: selected !== null,
    refetchInterval: streaming ? 1500 : false,
  });

  const auditQuery = useQuery({
    queryKey: ["audit", selected],
    queryFn: () => api.audit(selected!),
    enabled: selected !== null,
  });

  const state = dealQuery.data?.state ?? null;
  const running = dealQuery.data?.running ?? false;

  const stopStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStreaming(false);
    setReconnecting(false);
  }, []);

  /** Open the SSE stream after run/resume and drive the pipeline visualizer */
  const openStream = useCallback(
    (dealId: string) => {
      stopStream();
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
      setStreaming(true);
      setReconnecting(false);

      const es = new EventSource(`/api/deals/${encodeURIComponent(dealId)}/stream`);
      esRef.current = es;

      const handle = (e: MessageEvent) => {
        let parsed: StreamEvent;
        try {
          parsed = JSON.parse(e.data) as StreamEvent;
        } catch {
          parsed = { type: e.type };
        }
        parsed.type = e.type;
        setEvents((prev) => [...prev, parsed]);

        if (e.type === "interrupt") {
          const kind =
            (parsed.payload?.kind as string | undefined) ??
            mapNodeToInterruptKind(parsed.node ?? "");
          setInterrupt({
            node: kind,
            payload: (parsed.payload as Record<string, unknown> | undefined) ?? null,
          });
        }

        if (e.type === "node_finished" || e.type === "document_registered") {
          void queryClient.invalidateQueries({ queryKey: ["deal", dealId] });
        }
        if (e.type === "done" || e.type === "error") {
          if (e.type === "error") {
            setRunError("We couldn’t finish the review. Please try again.");
          }
          stopStream();
          void queryClient.invalidateQueries({ queryKey: ["deal", dealId] });
          void queryClient.invalidateQueries({ queryKey: ["audit", dealId] });
        }
      };

      for (const t of [
        "node_started",
        "node_finished",
        "interrupt",
        "deal_created",
        "document_registered",
        "done",
        "error",
      ]) {
        es.addEventListener(t, handle as EventListener);
      }

      es.onerror = (e) => {
        if ("data" in e && typeof (e as MessageEvent).data === "string") {
          try {
            JSON.parse((e as MessageEvent).data);
            setRunError("We couldn’t finish the review. Please try again.");
          } catch {
            setRunError("We couldn’t finish the review. Please try again.");
          }
          stopStream();
          return;
        }

        setReconnecting(true);
        void queryClient.invalidateQueries({ queryKey: ["deal", dealId] }).then(() => {
          const current = queryClient.getQueryData<{ state: unknown; running: boolean }>([
            "deal",
            dealId,
          ]);
          if (current && !current.running) {
            stopStream();
          }
        });
      };
    },
    [queryClient, stopStream],
  );

  useEffect(() => () => stopStream(), [stopStream]);

  const createDeal = useMutation({
    mutationFn: () => api.createDeal(),
    onSuccess: (res) => {
      setDeals((prev) => [res.deal_id, ...prev]);
      setSelected(res.deal_id);
      setEvents([]);
      setInterrupt(null);
      void queryClient.invalidateQueries({ queryKey: ["deal", res.deal_id] });
      toast.success("New deal created", { description: "Add your trade documents to get started." });
    },
    onError: (error) => toast.error("Could not create deal", { description: error.message }),
  });

  const runDeal = useMutation({
    mutationFn: (dealId: string) => api.runDeal(dealId),
    onSuccess: (_res, dealId) => openStream(dealId),
    onError: (e) => {
      const message = e instanceof Error ? e.message : String(e);
      setRunError(message);
      toast.error("Review could not start", { description: message });
    },
  });

  const readinessCheck = useMutation({
    mutationFn: (dealId: string) => api.checkReadiness(dealId),
    onSuccess: (result, dealId) => {
      queryClient.setQueryData(["deal", dealId], result);
      toast.success("Document check complete", { description: "Readiness results updated below." });
      void queryClient.invalidateQueries({ queryKey: ["audit", dealId] });
    },
    onError: (error) => toast.error("Could not check documents", { description: error.message }),
  });

  const removeDocument = useMutation({
    mutationFn: ({ dealId, docId }: { dealId: string; docId: string }) => api.removeDocument(dealId, docId),
    onSuccess: (_result, { dealId }) => {
      void queryClient.invalidateQueries({ queryKey: ["deal", dealId] });
      void queryClient.invalidateQueries({ queryKey: ["audit", dealId] });
      toast.success("Document removed from deal");
    },
    onError: (error) => toast.error("Could not remove document", { description: error.message }),
  });

  const handleUploadDocument = async (file: File, kind: DocKind) => {
    if (!selected) return;
    setUploading(true);
    try {
      await api.uploadDocument(selected, file, kind);
      toast.success("Document added", { description: file.name });
      void queryClient.invalidateQueries({ queryKey: ["deal", selected] });
      void queryClient.invalidateQueries({ queryKey: ["audit", selected] });
    } finally {
      setUploading(false);
    }
  };

  function selectDeal(id: string) {
    stopStream();
    setSelected(id);
    setEvents([]);
    setInterrupt(null);
    setRunError(null);
    setTab("overview");
  }

  const handleScenarioLoaded = (newDealId: string) => {
    setDeals((prev) => [newDealId, ...prev.filter((d) => d !== newDealId)]);
    setSelected(newDealId);
    setEvents([]);
    setInterrupt(null);
    setRunError(null);
    void queryClient.invalidateQueries({ queryKey: ["deal", newDealId] });
    runDeal.mutate(newDealId);
  };

  const copyDealId = () => {
    if (!selected) return;
    void navigator.clipboard.writeText(selected);
    setCopiedId(true);
    toast.success("Deal ID copied");
    setTimeout(() => setCopiedId(false), 1500);
  };

  const handleDeleteDeal = async (idToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Remove this deal from the list?",
      message: `Deal ${idToDelete} and its copilot conversations will be removed from this browser. The saved deal record and audit trail stay available.`,
      confirmLabel: "Remove deal",
    });
    if (!ok) return;
    const nextDeals = deals.filter((d) => d !== idToDelete);
    setDeals(nextDeals);
    localStorage.setItem(DEALS_KEY, JSON.stringify(nextDeals));
    clearCopilotHistory(idToDelete);
    if (selected === idToDelete) {
      const nextSelected = nextDeals[0] ?? null;
      setSelected(nextSelected);
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
    }
  };

  const handleClearAllDeals = async () => {
    if (deals.length === 0) return;
    const ok = await confirm({
      title: "Clear recent deals?",
      message: "Your recent deals and their copilot conversations will be removed from this browser. The saved deal records and audit trails stay available.",
      confirmLabel: "Clear history",
    });
    if (ok) {
      stopStream();
      setDeals([]);
      setSelected(null);
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
      localStorage.removeItem(DEALS_KEY);
      clearCopilotHistory();
    }
  };

  const showApprovalBar =
    (interrupt !== null || (state && (state.amendment_draft || state.escalation_reason))) &&
    !streaming &&
    state !== null &&
    !state.receipt;

  const openFindingsCount = state ? state.findings.filter((f) => f.status === "open").length : 0;
  const coreReadiness = documentReadiness(state);
  const coreUploaded = coreReadiness.filter((item) => item.uploaded).length;
  const unclassifiedCount = state?.documents.filter((doc) =>
    doc.kind === "unknown" && !state.extracted.some((extracted) => extracted.doc_id === doc.doc_id),
  ).length ?? 0;
  const visibleDeals = deals.filter((id) => id.toLowerCase().includes(dealSearch.trim().toLowerCase()));

  return (
    <div className="shell">
      {/* Sleek, Uncluttered Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <BrandLogo />
          <div className="brand-sub">Trade, made clearer</div>
        </div>

        {/* Primary workspace actions */}
        <div className="sidebar-actions" style={{ padding: "12px 14px" }}>
          <button
            className="btn btn-primary"
            onClick={() => createDeal.mutate()}
            disabled={createDeal.isPending}
            style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6 }}
          >
            <Plus size={14} />
            <span>{createDeal.isPending ? "Creating…" : "New deal"}</span>
          </button>

        </div>

        <section className="sidebar-readiness" aria-label="Document readiness">
          <div className="sidebar-readiness-head">
            <div><span className="sidebar-eyebrow">Deal setup</span><strong>{coreUploaded}/3 <small>core docs</small></strong></div>
            <button className="readiness-orbit" type="button" onClick={() => selected && setIsUploadModalOpen(true)} disabled={!selected} aria-label="Add deal documents" title={selected ? "Add deal documents" : "Select a deal first"} style={{ "--progress": `${(coreUploaded / 3) * 100}%` } as React.CSSProperties}>
              <FileUp size={15}/>
            </button>
          </div>
          <div className="sidebar-progress"><span style={{ width: `${(coreUploaded / 3) * 100}%` }}/></div>
          <p>{state ? "Recommended documents for a useful first review" : "Start a deal to build your document set"}</p>
          <div className="sidebar-readiness-list">
            {coreReadiness.map(({ requirement, uploaded, status, message }) => {
              const StatusIcon = status === "ready" ? CircleCheck : status === "review" ? CircleAlert : uploaded ? Clock3 : FileText;
              return <button key={requirement.kind} className={`sidebar-readiness-row ${status}`} onClick={() => {
                setTab("documents");
                if (!uploaded && selected) setIsUploadModalOpen(true);
              }} disabled={!selected} title={message}>
                <StatusIcon size={14}/><span>{requirement.label}</span><small>{uploaded ? status === "ready" ? "Ready" : status === "review" ? "Check" : "Added" : "Add"}</small>
              </button>;
            })}
          </div>
          {unclassifiedCount > 0 && <div className="sidebar-unclassified">{unclassifiedCount} file{unclassifiedCount === 1 ? "" : "s"} still need a document type</div>}
          <button className="sidebar-checklist-link" onClick={() => { setTab("documents"); if (selected) setIsUploadModalOpen(true); }} disabled={!selected}>
            Review documents and add files <ArrowRight size={13}/>
          </button>
        </section>

        {/* Deal History List */}
        <div className="deal-list">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 6px 6px" }}>
            <h3 style={{ margin: 0, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim)" }}>
              Recent Deals ({deals.length})
            </h3>
            {deals.length > 0 && (
              <button
                className="btn-link"
                onClick={() => void handleClearAllDeals()}
                title="Clear recent deals"
                style={{ fontSize: 10, color: "var(--text-faint)", cursor: "pointer", background: "none", border: "none", padding: "2px 4px" }}
              >
                Clear history
              </button>
            )}
          </div>
          {deals.length > 0 && <label className="deal-search"><Search size={14}/><input value={dealSearch} onChange={(event) => setDealSearch(event.target.value)} placeholder="Find a deal" aria-label="Find a recent deal"/></label>}
          {deals.length === 0 && (
            <div className="sidebar-empty">
              Your recent deals will appear here.
            </div>
          )}
          {visibleDeals.map((id) => (
            <div
              key={id}
              className={`deal-item ${id === selected ? "selected" : ""}`}
              onClick={() => selectDeal(id)}
              role="button"
              tabIndex={0}
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
              <span className="deal-id" title={id}>Deal · {id.slice(-6).toUpperCase()}</span>
                <span className="deal-meta">
                  <span>Sample deal</span>
                  {id === selected && (streaming || running) && (
                    <span className="live-dot" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Loader2 size={10} className="spinner" /> live
                    </span>
                  )}
                </span>
              </div>
              <button
                className="btn-link delete-deal-btn"
                onClick={(e) => void handleDeleteDeal(id, e)}
                title="Delete this deal from history"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-dim)",
                  opacity: 0.45,
                  cursor: "pointer",
                  padding: "4px 6px",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  flexShrink: 0,
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = "1";
                  e.currentTarget.style.color = "var(--status-block, #f43f5e)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = "0.45";
                  e.currentTarget.style.color = "var(--text-dim)";
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {deals.length > 0 && visibleDeals.length === 0 && <div className="sidebar-empty">No deals match “{dealSearch}”.</div>}
        </div>
        <div className="sidebar-assistant">
          <div><span className="sidebar-assistant-icon"><Sparkles size={15}/></span><span><strong>Need a hand?</strong><small>Ask about this deal</small></span></div>
          <button onClick={() => setCopilotOpen(true)}><MessageCircle size={15}/> Ask Copilot</button>
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="main">
        {/* Deal workspace header */}
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="topbar-title" style={{ fontSize: 14 }}>
              {selected ? `Deal · ${selected.slice(-6).toUpperCase()}` : "Your workspace"}
            </span>
            {selected && (
              <button
                className="btn-link mono faint"
                onClick={copyDealId}
            title="Copy deal reference"
                style={{ cursor: "pointer", color: "var(--text-dim)", display: "flex", alignItems: "center" }}
              >
                {copiedId ? <Check size={14} color="var(--status-pass)" /> : <Copy size={14} />}
              </button>
            )}
          </div>

          {/* Multi-Modal Status Badges */}
          {running && (
            <span className="chip" style={{ background: "rgba(6, 182, 212, 0.15)", color: "var(--accent-cyan)", border: "1px solid var(--accent-cyan)" }}>
              <Loader2 size={12} className="spinner" />
                <span>Reviewing</span>
            </span>
          )}
          {!running && state?.receipt && (
            <span className="chip chip-decision-allow">
              <CheckCircle2 size={12} />
              <span>Complete</span>
            </span>
          )}
          {!running && state?.escalation_reason && (
            <span className="chip chip-sev-block">
              <AlertOctagon size={12} />
              <span>Needs help</span>
            </span>
          )}
          {!running && interrupt && !state?.receipt && !state?.escalation_reason && (
            <span className="chip chip-sev-warn">
              <Lock size={12} />
              <span>Ready for your approval</span>
            </span>
          )}

          <span className="topbar-spacer" />

          {/* Sample data label */}
          <span className="badge-synthetic" title="ClearTrade operates entirely with synthetic demonstration data">
            <FlaskConical size={12} aria-hidden="true" />
            <span>DEMO DATA</span>
          </span>

          <button
            className="btn btn-secondary copilot-trigger"
            onClick={() => setCopilotOpen((open) => !open)}
            aria-expanded={copilotOpen}
          >
            <MessageCircle size={16} /> <span>Ask copilot</span>
          </button>
          <button
            className="btn btn-primary"
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            disabled={!selected || running || streaming}
            onClick={() => selected && runDeal.mutate(selected)}
          >
            {streaming || running ? (
              <>
                <Loader2 size={14} className="spinner" />
                <span>Checking documents…</span>
              </>
            ) : (
              <>
                <Play size={14} />
                <span>Review deal</span>
              </>
            )}
          </button>
        </header>

        {/* Tab Navigation */}
        <nav className="tabs">
          {TABS.filter((t) => ["overview", "findings", "documents"].includes(t.id)).map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              <span>{t.label}</span>
              {t.id === "findings" && openFindingsCount > 0 && (
                <span className="count" style={{ background: "var(--status-warn)", color: "#000" }}>
                  {openFindingsCount}
                </span>
              )}
              {t.id === "documents" && state && state.documents.length > 0 && (
                <span className="count">{state.documents.length}</span>
              )}
            </button>
          ))}
          <label className="details-select-label">More
            <select className="details-select" value={["fx", "cash", "audit"].includes(tab) ? tab : ""} onChange={(event) => event.target.value && setTab(event.target.value as TabId)}>
              <option value="" disabled>Choose a view</option>
              <option value="fx">FX routes</option>
              <option value="cash">Cash forecast</option>
              <option value="audit">Review history</option>
            </select>
          </label>
        </nav>

        {/* Content Area */}
        <div className={`content ${selected && tab === "overview" ? "content-overview" : ""}`}>
          {!selected ? (
            <section className="welcome-screen">
              <div className="welcome-copy">
                <div className="welcome-kicker"><span className="welcome-spark"><Sparkles size={14}/></span> CLEARTRADE · TRADE REVIEW</div>
                <h1>Make your next shipment<br/><em>ready to move.</em></h1>
                <p>Bring your trade documents together. ClearTrade checks them against the letter of credit, flags issues, and lays out the next step.</p>
                <div className="welcome-trust"><span><CheckCircle2 size={15}/> Document checks</span><span><CheckCircle2 size={15}/> Clear next steps</span></div>
              </div>
              <div className="welcome-start-card">
                <div className="welcome-card-heading"><div><span className="step-label">START HERE</span><h2>Try a deal</h2></div><span className="welcome-card-number">01</span></div>
                <p>Pick a sample and see the full review flow, including what happens when something needs attention.</p>
                <DemoScenarioLoader tenantId="demo-tenant" onScenarioLoaded={handleScenarioLoaded}/>
                <div className="welcome-divider"><span>or use your own documents</span></div>
                <button className="welcome-upload" onClick={async () => { try { await createDeal.mutateAsync(); setIsUploadModalOpen(true); } catch { /* The mutation displays its own toast. */ } }} disabled={createDeal.isPending}><FileUp size={16}/> Create a deal and upload documents <ArrowRight size={15}/></button>
              </div>
              <div className="welcome-bottom"><span>Built for cross-border trade teams</span><span>China <i/> Bangladesh <i/> Beyond</span></div>
            </section>
          ) : dealQuery.isLoading ? (
            <LoadingSkeleton rows={4} />
          ) : dealQuery.isError ? (
            <ErrorState
              title="Could Not Load Deal"
              message={String(dealQuery.error)}
              onRetry={() => dealQuery.refetch()}
            />
          ) : (
            <>
              {/* Sleek 5-Step Ribbon Visualizer (collapsed by default) */}
              {(streaming || events.length > 0 || running) && (
                <PipelineVisualizer
                  events={events}
                  running={streaming || running}
                  reconnecting={reconnecting}
                />
              )}

              {/* High-Clarity 1-Sentence Status & Action Banner */}
              {showApprovalBar && (
                <ApprovalBar
                  state={state!}
                  payload={
                    interrupt
                      ? { kind: interrupt.node as any, ...(interrupt.payload ?? {}) }
                      : null
                  }
                  onResumed={() => {
                    setInterrupt(null);
                    openStream(selected);
                  }}
                  onNavigateTab={(t) => setTab(t as TabId)}
                  currentTab={tab}
                />
              )}

              {runError && (
                <div style={{ marginBottom: 14 }}>
                  <ErrorState
                    title="The review stopped"
                    message={runError}
                    onRetry={() => runDeal.mutate(selected)}
                  />
                </div>
              )}

              {/* Tab Panel Content */}
              {state && (
                <>
                  {tab === "overview" && (
                    <Overview
                      state={state}
                      onNavigateTab={(t) => setTab(t as TabId)}
                      onRunDeal={() => selected && runDeal.mutate(selected)}
                      running={streaming || running}
                    />
                  )}
                  {tab === "findings" && (
                    <Findings
                      state={state}
                      onRunReview={() => selected && runDeal.mutate(selected)}
                      onUploadCorrectedDoc={async (file) => {
                        await api.uploadDocument(selected, file, "commercial_invoice");
                        await api.resume(selected, {
                          action: "corrected_document",
                          note: `Corrected document attached via Findings panel: ${file.name}`,
                        });
                        openStream(selected);
                      }}
                    />
                  )}
                  {tab === "fx" && <Fx state={state} onRunReview={() => selected && runDeal.mutate(selected)} onAddDocuments={() => setIsUploadModalOpen(true)} />}
                  {tab === "cash" && <CashFlow state={state} onRunReview={() => selected && runDeal.mutate(selected)} onAddDocuments={() => setIsUploadModalOpen(true)} />}
                  {tab === "documents" && <Documents state={state} onAddDocuments={() => setIsUploadModalOpen(true)} />}
                  {tab === "audit" && <Audit audit={auditQuery.data} state={state} />}
                </>
              )}
            </>
          )}
        </div>
      </main>

      {/* Modern Drag-and-Drop Document Upload Modal */}
      <UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUpload={handleUploadDocument}
        onRemoveDocument={async (docId) => {
          if (selected) await removeDocument.mutateAsync({ dealId: selected, docId });
        }}
        removingDocId={removeDocument.isPending ? removeDocument.variables?.docId ?? null : null}
        isUploading={uploading}
        state={state}
        isRunning={streaming || running}
        isChecking={readinessCheck.isPending}
        onCheckReadiness={async () => {
          if (!selected || !state?.documents.length || streaming || running) return;
          await readinessCheck.mutateAsync(selected);
        }}
      />
      <Copilot key={selected ?? "no-deal"} state={state} open={copilotOpen} onClose={() => setCopilotOpen(false)} dealId={selected} onDocumentUploaded={() => selected && void queryClient.invalidateQueries({ queryKey: ["deal", selected] })} onNavigate={setTab} />
      {confirmDialog}
    </div>
  );
}

function mapNodeToInterruptKind(node: string): string {
  if (node === "human_approval") return "human_approval";
  if (node === "await_corrected_doc" || node === "resolve_exception") return "await_corrected_doc";
  if (node === "escalate") return "escalate";
  return node || "human_approval";
}
