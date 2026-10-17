import { useState } from "react";
import type { AuditTrail, DealState } from "../api";
import { shortHash, formatMoney } from "../api";
import { DecisionChip } from "../ui";
import {
  ShieldCheck,
  ShieldAlert,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Link as LinkIcon,
  Activity,
  FileCheck,
  Shield,
  Cpu,
  CheckCircle2,
  XCircle,
} from "lucide-react";

export default function Audit({
  audit,
  state,
}: {
  audit: AuditTrail | undefined;
  state?: DealState | null;
}) {
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (!audit) {
    return (
      <div className="empty" style={{ padding: 32, textAlign: "center" }}>
        <Clock size={28} style={{ margin: "0 auto 8px", opacity: 0.5 }} />
        <div>Loading cryptographic audit trail…</div>
      </div>
    );
  }

  const copyHash = (hash: string) => {
    void navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 1500);
  };

  return (
    <div className="audit-panel" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* 1. Chain Status Verification Banner */}
      <div
        className={`audit-chain ${audit.chain_ok ? "ok" : "bad"}`}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "14px 18px",
          borderRadius: "var(--radius, 8px)",
          border: audit.chain_ok
            ? "1px solid rgba(16, 185, 129, 0.35)"
            : "1px solid rgba(244, 63, 94, 0.4)",
          background: audit.chain_ok
            ? "rgba(16, 185, 129, 0.08)"
            : "rgba(244, 63, 94, 0.12)",
          color: audit.chain_ok ? "var(--status-pass, #10b981)" : "var(--status-block, #f43f5e)",
        }}
      >
        {audit.chain_ok ? (
          <ShieldCheck size={22} aria-hidden="true" style={{ flexShrink: 0 }} />
        ) : (
          <ShieldAlert size={22} aria-hidden="true" style={{ flexShrink: 0 }} />
        )}
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>
            {audit.chain_ok
              ? "Audit Hash Chain Verified"
              : "CRITICAL: Audit Chain Broken"}
          </div>
          <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
            {audit.chain_ok
              ? `All ${audit.events.length} events are cryptographically linked via SHA-256 back-pointers. Zero tampering detected.`
              : "Events fail back-pointer verification — data may have been altered or skipped."}
          </div>
        </div>
        <span
          className="chip"
          style={{
            background: audit.chain_ok ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.2)",
            color: "inherit",
            border: "none",
            fontWeight: 700,
          }}
        >
          {audit.chain_ok ? "CHAIN OK" : "INTEGRITY VIOLATION"}
        </span>
      </div>

      {/* 2. Cryptographic Event Ledger */}
      {audit.events.length === 0 ? (
        <div className="empty" style={{ padding: 32, textAlign: "center" }}>
          <Activity size={28} style={{ margin: "0 auto 8px", opacity: 0.4 }} />
          <p>No audit events recorded yet.</p>
          <p className="faint" style={{ fontSize: 12 }}>
            Execute or run a deal to generate cryptographic state transitions.
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: "20px 24px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 16,
              borderBottom: "1px solid var(--border-subtle, #334155)",
              paddingBottom: 10,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 14, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim, #94a3b8)", display: "flex", alignItems: "center", gap: 8 }}>
              <FileCheck size={16} color="var(--accent-cyan, #06b6d4)" />
              Cryptographic Event Ledger ({audit.events.length} sequential blocks)
            </h2>
            <span className="faint mono" style={{ fontSize: 11 }}>
              Algorithm: SHA-256
            </span>
          </div>

          <div className="audit-timeline" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {audit.events.map((e, i) => {
              const isExpanded = expandedIndex === i;
              const hasPrevHash = Boolean((e as unknown as { prev_hash?: string }).prev_hash);
              const prevHash = (e as unknown as { prev_hash?: string }).prev_hash;

              return (
                <div
                  key={i}
                  style={{
                    border: "1px solid var(--border-subtle, #232d3b)",
                    borderRadius: 6,
                    background: "rgba(15, 23, 42, 0.6)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 12px",
                      cursor: "pointer",
                      userSelect: "none",
                      flexWrap: "wrap",
                    }}
                    onClick={() => setExpandedIndex(isExpanded ? null : i)}
                  >
                    <span style={{ color: "#64748b", display: "flex", alignItems: "center" }}>
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </span>

                    <span className="mono faint" style={{ fontSize: 11, minWidth: 140 }}>
                      {formatTimestamp(e.ts)}
                    </span>

                    <span className="chip chip-sev-info" style={{ fontSize: 11, fontWeight: 600 }}>
                      {e.kind}
                    </span>

                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                      {hasPrevHash && prevHash && (
                        <span
                          className="mono faint"
                          style={{ fontSize: 11, display: "inline-flex", alignItems: "center", gap: 4 }}
                          title={`Previous event hash: ${prevHash}`}
                        >
                          <LinkIcon size={10} />
                          prev:{shortHash(prevHash, 6)}
                        </span>
                      )}

                      <button
                        className="btn-link mono"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          background: "rgba(168, 85, 247, 0.1)",
                          color: "var(--accent-violet, #a855f7)",
                          border: "1px solid rgba(168, 85, 247, 0.25)",
                          borderRadius: 4,
                          padding: "2px 6px",
                          fontSize: 11,
                          cursor: "pointer",
                        }}
                        onClick={(ev) => {
                          ev.stopPropagation();
                          copyHash(e.hash);
                        }}
                        title={`Current hash: ${e.hash} (click to copy)`}
                      >
                        <span>hash:{shortHash(e.hash, 8)}</span>
                        {copiedHash === e.hash ? (
                          <Check size={11} color="var(--status-pass, #10b981)" />
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div
                      style={{
                        padding: "10px 14px",
                        background: "rgba(0, 0, 0, 0.35)",
                        borderTop: "1px solid rgba(255, 255, 255, 0.05)",
                        fontSize: 12,
                      }}
                    >
                      <div className="faint" style={{ marginBottom: 6, fontSize: 11, textTransform: "uppercase" }}>
                        Event Payload
                      </div>
                      <pre
                        className="mono"
                        style={{
                          margin: 0,
                          padding: "8px 10px",
                          background: "rgba(0, 0, 0, 0.4)",
                          borderRadius: 4,
                          border: "1px solid var(--border-subtle, #334155)",
                          overflowX: "auto",
                          maxHeight: 200,
                          color: "#cbd5e1",
                          fontSize: 11,
                        }}
                      >
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Cedar Policy Engine Formal Decision Trace */}
      {state && state.policy && (
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Shield size={16} color="var(--accent-cyan, #06b6d4)" />
            <h2 style={{ margin: 0, fontSize: 14, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim, #94a3b8)" }}>
              Cedar Policy Decision Trace
            </h2>
          </div>

          <div className="row" style={{ marginBottom: 12 }}>
            <DecisionChip decision={state.policy.decision} />
            <span className="muted" style={{ fontSize: 12 }}>
              Engine: <span className="mono">{state.policy.engine}</span>
            </span>
          </div>

          {state.policy.rules.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-subtle, #334155)", textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "8px 10px" }}>Rule Specification</th>
                    <th style={{ padding: "8px 10px" }}>Outcome</th>
                    <th style={{ padding: "8px 10px" }}>Evaluation Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {state.policy.rules.map((r) => (
                    <tr key={r.rule} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)" }}>
                      <td className="mono" style={{ padding: "8px 10px", fontWeight: 600 }}>
                        {r.rule}
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <span
                          className={`chip ${
                            r.allowed ? "chip-decision-allow" : "chip-sev-block"
                          }`}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11 }}
                        >
                          {r.allowed ? (
                            <CheckCircle2 size={12} />
                          ) : (
                            <XCircle size={12} />
                          )}
                          <span>{r.allowed ? "pass" : "fail"}</span>
                        </span>
                      </td>
                      <td className="muted" style={{ padding: "8px 10px" }}>{r.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 4. AI & Model Execution Ledger */}
      {state && state.served_by && state.served_by.length > 0 && (
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Cpu size={16} color="var(--accent-violet, #8b5cf6)" />
            <h2 style={{ margin: 0, fontSize: 14, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-dim, #94a3b8)" }}>
              AI Model Execution & Token Ledger
            </h2>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle, #334155)", textAlign: "left", color: "#94a3b8" }}>
                  <th style={{ padding: "8px 10px" }}>Graph Node</th>
                  <th style={{ padding: "8px 10px" }}>Alias</th>
                  <th style={{ padding: "8px 10px" }}>Deployment Served</th>
                  <th className="num" style={{ padding: "8px 10px", textAlign: "right" }}>Total Tokens</th>
                  <th className="num" style={{ padding: "8px 10px", textAlign: "right" }}>Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {state.served_by.map((m, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)" }}>
                    <td className="mono" style={{ padding: "8px 10px", fontWeight: 600 }}>{m.node}</td>
                    <td className="mono" style={{ padding: "8px 10px" }}>{m.alias}</td>
                    <td className="mono muted" style={{ padding: "8px 10px" }}>
                      {m.deployment} {m.degraded ? "(degraded)" : ""}
                    </td>
                    <td className="num tabular" style={{ padding: "8px 10px", textAlign: "right" }}>
                      {m.prompt_tokens + m.completion_tokens}
                    </td>
                    <td className="num tabular" style={{ padding: "8px 10px", textAlign: "right" }}>
                      {formatMoney(m.cost_minor, "USD")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  } catch {
    return ts;
  }
}
