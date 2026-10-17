import { useState } from "react";
import {
  CheckCircle2,
  Clock,
  PauseCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  WifiOff,
  Sparkles,
} from "lucide-react";
import type { StreamEvent } from "../api";
import { PIPELINE_STAGES } from "../config/pipelineStages";

interface PipelineVisualizerProps {
  events: StreamEvent[];
  running: boolean;
  reconnecting?: boolean;
}

export type NodeStatus = "idle" | "active" | "done" | "interrupted" | "failed";

export default function PipelineVisualizer({
  events,
  running,
  reconnecting = false,
}: PipelineVisualizerProps) {
  // Default to clean collapsed view for beginner-friendly uncluttered layout
  const [showDetails, setShowDetails] = useState(false);

  // Calculate node status and timing from events
  const nodeInfoMap = new Map<
    string,
    { status: NodeStatus; startTs?: string; finishTs?: string; elapsedMs?: number }
  >();

  for (const ev of events) {
    if (!ev.node) continue;
    const existing = nodeInfoMap.get(ev.node) || { status: "idle" };

    if (ev.type === "node_started") {
      existing.status = "active";
      existing.startTs = ev.ts;
    } else if (ev.type === "node_finished") {
      existing.status = "done";
      existing.finishTs = ev.ts;
      if (existing.startTs && ev.ts) {
        existing.elapsedMs = Math.max(
          0,
          Date.parse(ev.ts) - Date.parse(existing.startTs),
        );
      }
    } else if (ev.type === "interrupt") {
      existing.status = "interrupted";
    } else if (ev.type === "node_failed") {
      existing.status = "failed";
    }
    nodeInfoMap.set(ev.node, existing);
  }

  // Calculate stage-level statuses
  const stageStatuses = PIPELINE_STAGES.map((stage) => {
    const nodeStatuses = stage.nodes.map(
      (n) => nodeInfoMap.get(n.id)?.status || "idle",
    );
    const hasActive = nodeStatuses.includes("active");
    const hasFailed = nodeStatuses.includes("failed");
    const hasInterrupted = nodeStatuses.includes("interrupted");
    const isAllDone = stage.nodes
      .filter((n) => !n.isBranch)
      .every((n) => nodeInfoMap.get(n.id)?.status === "done");

    let status: NodeStatus = "idle";
    if (hasActive) status = "active";
    else if (hasFailed) status = "failed";
    else if (hasInterrupted) status = "interrupted";
    else if (isAllDone) status = "done";

    return { stage, status };
  });

  // Calculate overall headline summary
  const completedStagesCount = stageStatuses.filter((s) => s.status === "done").length;
  const currentActiveStage = stageStatuses.find((s) => s.status === "active" || s.status === "interrupted" || s.status === "failed");

  return (
    <div className="pipeline-stepper-container" style={{ marginBottom: 16 }}>
      {/* Top Header Summary & Toggle */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", color: "#94a3b8", textTransform: "uppercase" }}>
            Pipeline Progress
          </span>
          <span className="chip" style={{ fontSize: 11, background: "rgba(255,255,255,0.04)", border: "1px solid var(--border-subtle)" }}>
            {completedStagesCount} of 5 Stages Complete
          </span>
          {reconnecting && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
                color: "var(--status-warn)",
              }}
            >
              <WifiOff size={12} />
              <span>Reconnecting…</span>
            </span>
          )}
        </div>

        <button
          className="btn-link"
          onClick={() => setShowDetails(!showDetails)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontSize: 12,
            color: "var(--accent-cyan)",
            cursor: "pointer",
            background: "none",
            border: "none",
            padding: 0,
          }}
        >
          <span>{showDetails ? "Hide 16-Node Graph" : "View 16-Node Graph"}</span>
          {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Sleek Horizontal 5-Step Progress Ribbon */}
      <div
        className="pipeline-ribbon"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)",
          gap: 8,
          background: "var(--bg-card, #161e29)",
          border: "1px solid var(--border-subtle, #232d3b)",
          borderRadius: "var(--radius, 8px)",
          padding: "10px 12px",
        }}
      >
        {stageStatuses.map(({ stage, status }, index) => {
          const isDone = status === "done";
          const isActive = status === "active";
          const isInterrupted = status === "interrupted";
          const isFailed = status === "failed";

          let borderColor = "var(--border-subtle, #232d3b)";
          let bg = "rgba(0, 0, 0, 0.2)";
          let textColor = "var(--text-dim, #94a3b8)";

          if (isDone) {
            borderColor = "rgba(16, 185, 129, 0.35)";
            bg = "rgba(16, 185, 129, 0.06)";
            textColor = "var(--status-pass, #10b981)";
          } else if (isActive) {
            borderColor = "var(--accent-cyan, #06b6d4)";
            bg = "rgba(6, 182, 212, 0.08)";
            textColor = "var(--accent-cyan, #06b6d4)";
          } else if (isInterrupted) {
            borderColor = "var(--status-warn, #f59e0b)";
            bg = "rgba(245, 158, 11, 0.08)";
            textColor = "var(--status-warn, #f59e0b)";
          } else if (isFailed) {
            borderColor = "var(--status-block, #f43f5e)";
            bg = "rgba(244, 63, 94, 0.08)";
            textColor = "var(--status-block, #f43f5e)";
          }

          return (
            <div
              key={stage.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 10px",
                borderRadius: "var(--radius-sm, 6px)",
                border: `1px solid ${borderColor}`,
                background: bg,
                transition: "all 0.2s ease",
              }}
            >
              <div style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
                {isDone && <CheckCircle2 size={15} color="var(--status-pass, #10b981)" />}
                {isActive && <Loader2 size={15} className="spinner" color="var(--accent-cyan, #06b6d4)" />}
                {isInterrupted && <PauseCircle size={15} color="var(--status-warn, #f59e0b)" />}
                {isFailed && <XCircle size={15} color="var(--status-block, #f43f5e)" />}
                {status === "idle" && (
                  <div
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: "50%",
                      border: "1px solid var(--text-faint, #64748b)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 10,
                      color: "var(--text-faint, #64748b)",
                    }}
                  >
                    {index + 1}
                  </div>
                )}
              </div>

              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: textColor,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={stage.title}
                >
                  {stage.title}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--text-faint, #64748b)",
                    textTransform: "capitalize",
                    marginTop: 1,
                  }}
                >
                  {isDone ? "Completed" : isActive ? "Running…" : isInterrupted ? "Action Required" : isFailed ? "Halted" : "Queued"}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Optional Expanded 16-Node Technical Graph Drawer */}
      {showDetails && (
        <div
          className="pipeline-stages-container"
          style={{
            marginTop: 12,
            padding: 12,
            background: "rgba(11, 15, 20, 0.7)",
            border: "1px solid var(--border-subtle, #232d3b)",
            borderRadius: "var(--radius, 8px)",
          }}
        >
          {PIPELINE_STAGES.map((stage) => (
            <div key={stage.id} className="pipeline-stage-block">
              <div className="pipeline-stage-header" style={{ cursor: "default" }}>
                <span style={{ fontSize: 11, fontWeight: 600 }}>{stage.title}</span>
              </div>
              <div className="pipeline-nodes-list">
                {stage.nodes.map((node) => {
                  const info = nodeInfoMap.get(node.id);
                  const status: NodeStatus = info?.status || "idle";
                  const isVisited = status !== "idle";
                  const isBranch = Boolean(node.isBranch);

                  return (
                    <div
                      key={node.id}
                      className={`pipeline-node-chip status-${status} ${
                        isBranch ? "is-branch" : ""
                      } ${!isVisited && isBranch ? "branch-unvisited" : ""}`}
                      title={`${node.description}${
                        info?.elapsedMs !== undefined ? ` (${info.elapsedMs}ms)` : ""
                      }`}
                    >
                      <div className="node-icon">
                        {status === "active" && (
                          <Loader2 size={12} className="spinner" />
                        )}
                        {status === "done" && <CheckCircle2 size={12} />}
                        {status === "interrupted" && <PauseCircle size={12} />}
                        {status === "failed" && <XCircle size={12} />}
                        {status === "idle" && <Clock size={12} opacity={0.4} />}
                      </div>

                      <span className="node-label">{node.label}</span>

                      {info?.elapsedMs !== undefined && info.elapsedMs > 0 && (
                        <span className="node-elapsed">{info.elapsedMs}ms</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
