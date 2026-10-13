import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DocKind, StreamEvent } from "./api";
import { api } from "./api";
import ApprovalBar from "./components/ApprovalBar";
import Ticker from "./components/Ticker";
import Overview from "./panels/Overview";
import Findings from "./panels/Findings";
import Fx from "./panels/Fx";
import CashFlow from "./panels/CashFlow";
import Documents from "./panels/Documents";
import Audit from "./panels/Audit";

const DEALS_KEY = "cleartrade.deals";
const DOC_KINDS: DocKind[] = [
  "letter_of_credit",
  "commercial_invoice",
  "packing_list",
  "bill_of_lading",
];

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
  /** node name the backend reports on the SSE interrupt event */
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
  const [tenantId, setTenantId] = useState("demo-tenant");
  const [uploadKind, setUploadKind] = useState<DocKind>("letter_of_credit");
  const [hasFile, setHasFile] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [interrupt, setInterrupt] = useState<InterruptState | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
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
    esRef.current?.close();
    esRef.current = null;
    setStreaming(false);
  }, []);

  /** Open the SSE stream after run/resume and drive the ticker. */
  const openStream = useCallback(
    (dealId: string) => {
      esRef.current?.close();
      setEvents([]);
      setInterrupt(null);
      setRunError(null);
      setStreaming(true);

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
          if (e.type === "error") setRunError(parsed.detail ?? "run failed");
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
      es.onerror = () => {
        // the server closes the stream after done/error; onerror also fires
        // on transient drops — only surface it if we never finished
        stopStream();
      };
    },
    [queryClient, stopStream],
  );

  useEffect(() => () => esRef.current?.close(), []);

  const createDeal = useMutation({
    mutationFn: () => api.createDeal(tenantId),
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

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(selected!, file, uploadKind),
    onSuccess: () => {
      if (fileRef.current) fileRef.current.value = "";
      setHasFile(false);
      void queryClient.invalidateQueries({ queryKey: ["deal", selected] });
      void queryClient.invalidateQueries({ queryKey: ["audit", selected] });
    },
  });

  function selectDeal(id: string) {
    stopStream();
    setSelected(id);
    setEvents([]);
    setInterrupt(null);
    setRunError(null);
    setTab("overview");
  }

  const showApprovalBar =
    interrupt !== null && !streaming && state !== null && !state.receipt;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-name">
            <span className="mark">CT</span> ClearTrade
          </div>
          <div className="brand-sub">export deal pre-flight</div>
        </div>

        <div className="sidebar-actions">
          <div className="row" style={{ gap: 6 }}>
            <input
              style={{ flex: 1, minWidth: 0 }}
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="tenant id"
              aria-label="Tenant id"
            />
            <button
              className="btn btn-primary"
              onClick={() => createDeal.mutate()}
              disabled={createDeal.isPending}
            >
              {createDeal.isPending ? "…" : "+ New deal"}
            </button>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <select
              style={{ flex: 1, minWidth: 0 }}
              value={uploadKind}
              onChange={(e) => setUploadKind(e.target.value as DocKind)}
              aria-label="Document kind"
            >
              {DOC_KINDS.map((k) => (
                <option key={k} value={k}>
                  {kindLabel(k)}
                </option>
              ))}
            </select>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              style={{ maxWidth: 150 }}
              onChange={(e) => setHasFile(e.target.files !== null && e.target.files.length > 0)}
            />
          </div>
          <button
            className="btn"
            disabled={!selected || upload.isPending || !hasFile}
            onClick={() => {
              const f = fileRef.current?.files?.[0];
              if (f) upload.mutate(f);
            }}
          >
            {upload.isPending ? "Uploading…" : "Upload document into deal"}
          </button>
          {upload.isError && (
            <span className="error-text">{String(upload.error)}</span>
          )}
        </div>

        <div className="deal-list">
          <h3>Deals ({deals.length})</h3>
          {deals.length === 0 && (
            <div className="sidebar-empty">No deals yet — create one to begin.</div>
          )}
          {deals.map((id) => (
            <button
              key={id}
              className={`deal-item ${id === selected ? "selected" : ""}`}
              onClick={() => selectDeal(id)}
            >
              <span className="deal-id">{id}</span>
              <span className="deal-meta">
                <span>tenant {tenantId}</span>
                {id === selected && streaming && <span className="live-dot">live</span>}
              </span>
            </button>
          ))}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <span className="topbar-title mono">{selected ?? "No deal selected"}</span>
          {running && <span className="live-dot">running</span>}
          {dealQuery.data?.running === false && state?.receipt && (
            <span className="chip chip-decision-allow">executed</span>
          )}
          {state?.escalation_reason && <span className="chip chip-sev-block">escalated</span>}
          <span className="topbar-spacer" />
          <span className="badge-synthetic">SYNTHETIC DATA</span>
          <button
            className="btn btn-primary"
            disabled={!selected || running || streaming}
            onClick={() => selected && runDeal.mutate(selected)}
          >
            {streaming ? "Streaming…" : running ? "Running…" : "Run deal"}
          </button>
        </header>

        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === "findings" && state && state.findings.length > 0 && (
                <span className="count">{state.findings.length}</span>
              )}
              {t.id === "documents" && state && state.documents.length > 0 && (
                <span className="count">{state.documents.length}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="content">
          {!selected && (
            <div className="placeholder">
              Create a deal in the sidebar, upload its trade documents, then press “Run deal”.
              Every number in this console is synthetic demo data.
            </div>
          )}

          {selected && showApprovalBar && interrupt && (
            <ApprovalBar
              state={state!}
              payload={
                interrupt.node === "human_approval"
                  ? { kind: "human_approval", ...(interrupt.payload ?? {}) }
                  : interrupt.node === "await_corrected_doc"
                    ? { kind: "await_corrected_doc", ...(interrupt.payload ?? {}) }
                    : { kind: interrupt.node, ...(interrupt.payload ?? {}) }
              }
              onResumed={() => {
                setInterrupt(null);
                openStream(selected);
              }}
            />
          )}

          {selected && (streaming || events.length > 0) && (
            <Ticker events={events} running={streaming} />
          )}

          {runError && (
            <p className="error-text" style={{ marginTop: 0 }}>
              {runError}
            </p>
          )}

          {selected &&
            (dealQuery.isLoading ? (
              <div className="placeholder">Loading deal…</div>
            ) : dealQuery.isError ? (
              <div className="placeholder error-text">
                Could not load deal: {String(dealQuery.error)} — is the backend running?
              </div>
            ) : state ? (
              <>
                {tab === "overview" && <Overview state={state} />}
                {tab === "findings" && <Findings state={state} />}
                {tab === "fx" && <Fx state={state} />}
                {tab === "cash" && <CashFlow state={state} />}
                {tab === "documents" && <Documents state={state} />}
                {tab === "audit" && <Audit audit={auditQuery.data} />}
              </>
            ) : null)}
        </div>
      </main>
    </div>
  );
}

function mapNodeToInterruptKind(node: string): string {
  if (node === "human_approval") return "human_approval";
  if (node === "await_corrected_doc" || node === "resolve_exception") return "await_corrected_doc";
  if (node === "escalate") return "escalate";
  return node || "human_approval";
}

function kindLabel(k: DocKind): string {
  switch (k) {
    case "letter_of_credit":
      return "Letter of credit";
    case "commercial_invoice":
      return "Commercial invoice";
    case "packing_list":
      return "Packing list";
    case "bill_of_lading":
      return "Bill of lading";
    default:
      return "Unknown";
  }
}
