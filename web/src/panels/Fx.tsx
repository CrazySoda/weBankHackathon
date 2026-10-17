import type { DealState } from "../api";
import { formatMoney } from "../api";
import { SyntheticChip } from "../ui";
import { TrendingUp, ArrowLeftRight, CheckCircle2, ShieldCheck, Zap } from "lucide-react";

function formatRate(scaled: number): string {
  const s = BigInt(scaled).toString().padStart(7, "0");
  const whole = s.slice(0, s.length - 6) || "0";
  const frac = s.slice(-6);
  return `${whole}.${frac}`;
}

const ROUTE_LABELS: Record<string, { label: string; desc: string; icon: React.ElementType }> = {
  "route-offshore-cips": {
    label: "Offshore RMB Net Settlement (CIPS)",
    desc: "Direct cross-border clearing via CIPS corridor. Minimal intermediary spread.",
    icon: Zap,
  },
  "route-standard-wire": {
    label: "Standard Commercial Bank TT Wire",
    desc: "Traditional correspondent banking routing. Standard SWIFT transfer fee applies.",
    icon: ArrowLeftRight,
  },
  "route-trade-finance": {
    label: "Discounted Trade Financing Settlement",
    desc: "Upfront capital advance at agreed discount rate. Eliminates 90-day credit risk.",
    icon: TrendingUp,
  },
};

export default function Fx({ state }: { state: DealState }) {
  if (state.fx_options.length === 0) {
    return <div className="card empty">No FX quotes evaluated yet — run the deal to evaluate.</div>;
  }

  // Sort by net_minor descending (best first)
  const sorted = [...state.fx_options].sort((a, b) => b.net_minor - a.net_minor);
  const bestRoute = sorted[0];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16 }}>FX Route Comparison & Settlement Optimization</h2>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--text-dim, #94a3b8)" }}>
            Real-time ranked settlement routes comparing net proceeds and basis point spreads
          </p>
        </div>
        <SyntheticChip />
      </div>

      {/* 3 Ranked Cards */}
      <div className="fx-cards-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginBottom: 18 }}>
        {sorted.map((route, idx) => {
          const isBest = idx === 0;
          const info = ROUTE_LABELS[route.route_id] || {
            label: route.provider,
            desc: "Custom trade settlement route",
            icon: ArrowLeftRight,
          };
          const Icon = info.icon;

          return (
            <div
              key={route.route_id}
              className={`fx-route-card ${isBest ? "is-best-route" : ""}`}
              style={{
                background: "var(--bg-card, #161e29)",
                border: isBest
                  ? "2px solid var(--accent-cyan, #06b6d4)"
                  : "1px solid var(--border-subtle, #232d3b)",
                borderRadius: "var(--radius, 10px)",
                padding: "16px",
                position: "relative",
                boxShadow: isBest ? "0 0 16px rgba(6, 182, 212, 0.15)" : undefined,
              }}
            >
              {isBest && (
                <div
                  style={{
                    position: "absolute",
                    top: -10,
                    right: 14,
                    background: "var(--accent-cyan, #06b6d4)",
                    color: "#0b0f14",
                    fontSize: 10,
                    fontWeight: 800,
                    padding: "2px 8px",
                    borderRadius: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  <CheckCircle2 size={11} />
                  <span>Recommended Route</span>
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ color: isBest ? "var(--accent-cyan, #06b6d4)" : "var(--text-dim, #94a3b8)" }}>
                  <Icon size={18} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{info.label}</h3>
                  <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-faint, #64748b)" }}>
                    {route.provider} · {route.sell_currency}/{route.buy_currency}
                  </span>
                </div>
              </div>

              <div style={{ margin: "14px 0" }}>
                <div style={{ fontSize: 11, color: "var(--text-dim, #94a3b8)", textTransform: "uppercase" }}>
                  Estimated Net Proceeds
                </div>
                <div
                  style={{
                    fontSize: 22,
                    fontWeight: 800,
                    fontFamily: "var(--mono)",
                    color: isBest ? "var(--accent-cyan, #06b6d4)" : "var(--text, #e6ebf2)",
                  }}
                  className="tabular"
                >
                  {formatMoney(route.net_minor, route.buy_currency)}
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  padding: "10px",
                  background: "var(--bg-base, #0b0f14)",
                  borderRadius: "var(--radius-sm, 6px)",
                  fontSize: 12,
                  marginBottom: 10,
                }}
              >
                <div>
                  <span className="muted">Effective Rate:</span>
                  <div className="mono tabular" style={{ fontWeight: 600 }}>
                    {formatRate(route.effective_rate_scaled)}
                  </div>
                </div>
                <div>
                  <span className="muted">Spread:</span>
                  <div className="mono tabular" style={{ fontWeight: 600 }}>
                    {route.spread_bp} bps
                  </div>
                </div>
              </div>

              <p style={{ margin: 0, fontSize: 11, color: "var(--text-dim, #94a3b8)", lineHeight: 1.35 }}>
                {info.desc}
              </p>
            </div>
          );
        })}
      </div>

      {/* Summary Table */}
      <div className="card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>Full Quote Audit Breakdown</h3>
        <table>
          <thead>
            <tr>
              <th>Route ID</th>
              <th>Provider</th>
              <th>Currency Pair</th>
              <th className="num">Gross Face Amount</th>
              <th className="num">Fee</th>
              <th className="num">Spread (bps)</th>
              <th className="num">Net Proceeds</th>
              <th className="num">Rate</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((o, idx) => (
              <tr key={o.route_id} className={idx === 0 ? "best" : undefined}>
                <td className="mono">{o.route_id}</td>
                <td>
                  {o.provider}
                  {idx === 0 && <span className="best-tag">BEST</span>}
                </td>
                <td className="mono muted">
                  {o.sell_currency}/{o.buy_currency}
                </td>
                <td className="num tabular">{formatMoney(o.amount_minor, o.sell_currency)}</td>
                <td className="num tabular">{formatMoney(o.fee_minor, o.sell_currency)}</td>
                <td className="num tabular">{o.spread_bp} bp</td>
                <td className="num tabular" style={{ fontWeight: idx === 0 ? 700 : undefined }}>
                  {formatMoney(o.net_minor, o.buy_currency)}
                </td>
                <td className="num mono tabular">{formatRate(o.effective_rate_scaled)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
