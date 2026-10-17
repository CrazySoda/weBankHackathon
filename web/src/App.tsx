import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DocKind, StreamEvent } from "./api";
import { api, shortHash } from "./api";
import ApprovalBar from "./components/ApprovalBar";
import PipelineVisualizer from "./components/PipelineVisualizer";
import DemoScenarioLoader from "./components/DemoScenarioLoader";
import UploadModal from "./components/UploadModal";
import { LoadingSkeleton, EmptyState, ErrorState } from "./components/StateViews";
import Overview from "./panels/Overview";
import Findings from "./panels/Findings";
import Fx from "./panels/Fx";
import CashFlow from "./panels/CashFlow";
import Documents from "./panels/Documents";
import Audit from "./panels/Audit";
import {
  FlaskConical,
  Play,
  Loader2,
  CheckCircle2,
  AlertOctagon,
  Clock,
  Plus,
  FileUp,
  Layers,
  Copy,
  Check,
  Lock,
  Trash2,
} from "lucide-react";

const DEALS_KEY = "cleartrade.deals";

type TabId = "overview" | "findings" | "fx" | "cash" | "documents" | "audit";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "findings", label: "Findings" },
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
  const [deals, setDeals] = useState<string[]>(loadDeals);
  const [selected, setSelected] = useState<string | null>(() => loadDeals()[0] ?? null);
  const [tab, setTab] = useState<TabId>("overview");
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

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
            setRunError(parsed.detail ?? "Pipeline execution halted with an error");
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
            const errData = JSON.parse((e as MessageEvent).data);
            setRunError(errData.detail ?? "Pipeline execution error");
          } catch {
            setRunError("Server stream error");
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
    },
  });

  const runDeal = useMutation({
    mutationFn: (dealId: string) => api.runDeal(dealId),
    onSuccess: (_res, dealId) => openStream(dealId),
    onError: (e) => setRunError(e instanceof Error ? e.message : String(e)),
  });

  const handleUploadDocument = async (file: File, kind: DocKind) => {
    if (!selected) return;
    await api.uploadDocument(selected, file, kind);
    void queryClient.invalidateQueries({ queryKey: ["deal", selected] });
    void queryClient.invalidateQueries({ queryKey: ["audit", selected] });
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
    setTimeout(() => setCopiedId(false), 1500);
  };

  const handleDeleteDeal = (idToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextDeals = deals.filter((d) => d !== idToDelete);
    setDeals(nextDeals);
    localStorage.setItem(DEALS_KEY, JSON.stringify(nextDeals));
    if (selected === idToDelete) {
      const nextSelected = nextDeals[0] ?? null;
      setSelected(nextSelected);
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
    }
  };

  const handleClearAllDeals = () => {
    if (deals.length === 0) return;
    if (window.confirm("Clear all deals from console history?")) {
      stopStream();
      setDeals([]);
      setSelected(null);
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
      localStorage.removeItem(DEALS_KEY);
    }
  };

  const showApprovalBar =
    (interrupt !== null || (state && (state.amendment_draft || state.escalation_reason))) &&
    !streaming &&
    state !== null &&
    !state.receipt;

  const openFindingsCount = state ? state.findings.filter((f) => f.status === "open").length : 0;

  return (
    <div className="shell">
      {/* Sleek, Uncluttered Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-name">
            <span className="mark">CT</span> ClearTrade
          </div>
          <div className="brand-sub">institutional trade finance engine</div>
        </div>

        {/* 1-Click Demo Scenarios */}
        <div style={{ padding: "12px 14px 4px", borderBottom: "1px solid var(--border-subtle)" }}>
          <DemoScenarioLoader
            tenantId="demo-tenant"
            onScenarioLoaded={handleScenarioLoaded}
          />
        </div>

        {/* Clean Action Buttons */}
        <div className="sidebar-actions" style={{ padding: "12px 14px" }}>
          <button
            className="btn btn-primary"
            onClick={() => createDeal.mutate()}
            disabled={createDeal.isPending}
            style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, marginBottom: 8 }}
          >
            <Plus size={14} />
            <span>{createDeal.isPending ? "Creating…" : "New Empty Deal"}</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={() => setIsUploadModalOpen(true)}
            disabled={!selected}
            style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6 }}
            title={selected ? "Attach trade document" : "Select a deal first to upload documents"}
          >
            <FileUp size={14} />
            <span>Upload Document…</span>
          </button>
        </div>

        {/* Deal History List */}
        <div className="deal-list">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 6px 6px" }}>
            <h3 style={{ margin: 0, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim)" }}>
              Recent Deals ({deals.length})
            </h3>
            {deals.length > 0 && (
              <button
                className="btn-link"
                onClick={handleClearAllDeals}
                title="Clear all deals from history"
                style={{ fontSize: 10, color: "var(--text-faint)", cursor: "pointer", background: "none", border: "none", padding: "2px 4px" }}
              >
                Clear All
              </button>
            )}
          </div>
          {deals.length === 0 && (
            <div className="sidebar-empty">
              No deals yet. Click a demo scenario above to test the verification pipeline.
            </div>
          )}
          {deals.map((id) => (
            <div
              key={id}
              className={`deal-item ${id === selected ? "selected" : ""}`}
              onClick={() => selectDeal(id)}
              role="button"
              tabIndex={0}
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <span className="deal-id">{id}</span>
                <span className="deal-meta">
                  <span>synthetic</span>
                  {id === selected && (streaming || running) && (
                    <span className="live-dot" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Loader2 size={10} className="spinner" /> live
                    </span>
                  )}
                </span>
              </div>
              <button
                className="btn-link delete-deal-btn"
                onClick={(e) => handleDeleteDeal(id, e)}
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
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="main">
        {/* Institutional Top Bar */}
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="topbar-title mono" style={{ fontSize: 14 }}>
              {selected ?? "No deal selected"}
            </span>
            {selected && (
              <button
                className="btn-link mono faint"
                onClick={copyDealId}
                title="Copy Deal ID"
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
              <span>RUNNING</span>
            </span>
          )}
          {!running && state?.receipt && (
            <span className="chip chip-decision-allow">
              <CheckCircle2 size={12} />
              <span>EXECUTED</span>
            </span>
          )}
          {!running && state?.escalation_reason && (
            <span className="chip chip-sev-block">
              <AlertOctagon size={12} />
              <span>ESCALATED</span>
            </span>
          )}
          {!running && interrupt && !state?.receipt && !state?.escalation_reason && (
            <span className="chip chip-sev-warn">
              <Lock size={12} />
              <span>APPROVAL PENDING</span>
            </span>
          )}

          <span className="topbar-spacer" />

          {/* Permanent Synthetic Data Badge */}
          <span className="badge-synthetic" title="ClearTrade operates entirely with synthetic demonstration data">
            <FlaskConical size={12} aria-hidden="true" />
            <span>SYNTHETIC DATA</span>
          </span>

          <button
            className="btn btn-primary"
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            disabled={!selected || running || streaming}
            onClick={() => selected && runDeal.mutate(selected)}
          >
            {streaming || running ? (
              <>
                <Loader2 size={14} className="spinner" />
                <span>Running Pipeline…</span>
              </>
            ) : (
              <>
                <Play size={14} />
                <span>Run Deal</span>
              </>
            )}
          </button>
        </header>

        {/* Tab Navigation */}
        <nav className="tabs">
          {TABS.map((t) => (
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
        </nav>

        {/* Content Area */}
        <div className="content">
          {!selected ? (
            <EmptyState
              title="No Deal Selected"
              message="Choose a 1-click demo scenario from the sidebar or create a new deal to run the trade finance pre-flight engine."
              icon={Layers}
            />
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
                />
              )}

              {runError && (
                <div style={{ marginBottom: 14 }}>
                  <ErrorState
                    title="Pipeline Interruption"
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
                      onUploadCorrectedDoc={async (file, kind) => {
                        await api.uploadDocument(selected, file, kind);
                        await api.resume(selected, {
                          action: "corrected_document",
                          note: `Corrected document attached via Findings panel: ${file.name}`,
                        });
                        openStream(selected);
                      }}
                    />
                  )}
                  {tab === "fx" && <Fx state={state} />}
                  {tab === "cash" && <CashFlow state={state} />}
                  {tab === "documents" && <Documents state={state} />}
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
        isUploading={false}
      />
    </div>
  );
}

function mapNodeToInterruptKind(node: string): string {
  if (node === "human_approval") return "human_approval";
  if (node === "await_corrected_doc" || node === "resolve_exception") return "await_corrected_doc";
  if (node === "escalate") return "escalate";
  return node || "human_approval";
}
