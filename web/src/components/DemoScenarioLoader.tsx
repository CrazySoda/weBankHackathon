import { useState } from "react";
import { CheckCircle2, FileWarning, ShieldAlert, Bug, Loader2, Sparkles } from "lucide-react";
import { api } from "../api";

export type ScenarioType = "clean" | "discrepancy" | "mismatch" | "injection";

interface DemoScenarioLoaderProps {
  tenantId: string;
  onScenarioLoaded: (dealId: string) => void;
}

const SCENARIOS = [
  {
    id: "clean" as ScenarioType,
    label: "Clean deal",
    fullName: "Clean Deal",
    seed: "seed-01",
    desc: "See a clean review reach approval.",
    icon: CheckCircle2,
    badgeColor: "var(--status-pass, #10b981)",
  },
  {
    id: "discrepancy" as ScenarioType,
    label: "Invoice discrepancy",
    fullName: "Fixable Discrepancy",
    seed: "seed-06",
    desc: "See how to fix an invoice amount mismatch.",
    icon: FileWarning,
    badgeColor: "var(--status-warn, #f59e0b)",
  },
  {
    id: "mismatch" as ScenarioType,
    label: "Beneficiary mismatch",
    fullName: "Beneficiary Mismatch",
    seed: "seed-08",
    desc: "See how ClearTrade handles a critical mismatch.",
    icon: ShieldAlert,
    badgeColor: "var(--status-block, #f43f5e)",
  },
  {
    id: "injection" as ScenarioType,
    label: "Suspicious document",
    fullName: "Prompt Injection",
    seed: "poison-01",
    desc: "See document security screening in action.",
    icon: Bug,
    badgeColor: "var(--status-block, #f43f5e)",
  },
];

export default function DemoScenarioLoader({
  tenantId,
  onScenarioLoaded,
}: DemoScenarioLoaderProps) {
  const [loadingScenario, setLoadingScenario] = useState<ScenarioType | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (tenantId !== "demo-tenant") {
    return null;
  }

  const handleSelectScenario = async (scenario: ScenarioType) => {
    try {
      setLoadingScenario(scenario);
      setError(null);
      const res = await api.demoSeed(scenario);
      onScenarioLoaded(res.deal_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load demo scenario");
    } finally {
      setLoadingScenario(null);
    }
  };

  return (
    <div className="demo-scenario-container">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 8,
          fontSize: 11,
          fontWeight: 700,
          color: "var(--text-dim, #94a3b8)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        <Sparkles size={13} color="var(--accent-cyan, #06b6d4)" />
        <span>1-Click Scenarios</span>
      </div>

      {/* 2x2 Compact Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        {SCENARIOS.map((sc) => {
          const Icon = sc.icon;
          const isLoading = loadingScenario === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => handleSelectScenario(sc.id)}
              disabled={loadingScenario !== null}
              className="demo-scenario-btn"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "7px 8px",
                background: "rgba(0, 0, 0, 0.25)",
                border: "1px solid var(--border-subtle, #232d3b)",
                borderRadius: "var(--radius-sm, 6px)",
                color: "var(--text, #e2e8f0)",
                cursor: loadingScenario !== null ? "not-allowed" : "pointer",
                textAlign: "left",
                transition: "all 0.15s ease",
              }}
              title={`${sc.fullName}: ${sc.desc}`}
            >
              <div style={{ color: sc.badgeColor, display: "flex", alignItems: "center", flexShrink: 0 }}>
                {isLoading ? (
                  <Loader2 size={13} className="spinner" />
                ) : (
                  <Icon size={13} />
                )}
              </div>
              <span className="scenario-copy">
                <strong>{sc.label}</strong>
                <small>{sc.desc}</small>
              </span>
            </button>
          );
        })}
      </div>

      {error && (
        <div
          style={{
            marginTop: 6,
            fontSize: 11,
            color: "var(--status-block, #f43f5e)",
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
