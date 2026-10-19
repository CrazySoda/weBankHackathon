import type { DealState } from "../api";
import { formatMoney } from "../api";
import { SyntheticChip } from "../ui";
import { TrendingUp, ArrowLeftRight, CheckCircle2, Zap } from "lucide-react";
import GuidedEmptyState from "../components/GuidedEmptyState";

function formatRate(scaled: number): string {
  const s = BigInt(scaled).toString().padStart(7, "0");
  const whole = s.slice(0, s.length - 6) || "0";
  const frac = s.slice(-6);
  return `${whole}.${frac}`;
}

const ROUTE_LABELS: Record<string, { label: string; desc: string; icon: React.ElementType }> = {
  "wire-usd-hk": {
    label: "Hong Kong bank wire",
    desc: "A synthetic USD to CNY bank wire quote through Hong Kong.",
    icon: Zap,
  },
  "cny-direct": {
    label: "Direct CNY settlement",
    desc: "A synthetic quote for settling directly in Chinese yuan.",
    icon: ArrowLeftRight,
  },
  "forward-lock": {
    label: "Forward rate lock",
    desc: "A synthetic quote that locks an exchange rate for settlement.",
    icon: TrendingUp,
  },
};

export default function Fx({
  state,
  selectedRoute,
  onSelectRoute,
  onRunReview,
  onAddDocuments,
}: {
  state: DealState;
  /** The route the approver picked (null = the recommended one). */
  selectedRoute?: string | null;
  /** Present only while the deal is waiting for approval; absent = comparison only. */
  onSelectRoute?: (routeId: string | null) => void;
  onRunReview?: () => void;
  onAddDocuments?: () => void;
}) {
  if (state.fx_options.length === 0) {
    const hasDocuments = state.documents.length > 0;
    const reviewed = Boolean(state.check_plan);
    return <GuidedEmptyState
      icon={ArrowLeftRight}
      eyebrow="Payment options"
      title={reviewed ? "No payment routes found" : hasDocuments ? "Compare your payment routes" : "Start with your trade documents"}
      description={reviewed
        ? "We couldn't calculate a route from the details found. Check the invoice amount and currencies, then try again."
        : "See estimated proceeds, exchange rates, and fees side by side once your deal has been reviewed."}
      actionLabel={reviewed ? "Check documents" : hasDocuments ? "Run deal review" : "Add documents"}
      onAction={reviewed ? onAddDocuments : hasDocuments ? onRunReview : onAddDocuments}
      steps={["Add your trade documents", "Review deal details", "Compare estimated payouts"]}
      footnote="Routes shown here use sample market data."
    />;
  }

  // Sort by net_minor descending (best first)
  const sorted = [...state.fx_options].sort((a, b) => b.net_minor - a.net_minor);
  const chosenId =
    selectedRoute && sorted.some((o) => o.route_id === selectedRoute)
      ? selectedRoute
      : sorted[0].route_id;
  const proceedsByCurrency = sorted.reduce((groups, route) => {
    const current = groups.get(route.buy_currency) ?? [];
    current.push(route);
    groups.set(route.buy_currency, current);
    return groups;
  }, new Map<string, typeof sorted>());

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16 }}>Payment route comparison</h2>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--text-dim, #94a3b8)" }}>
            {onSelectRoute
              ? "Click a card to choose the route to pay through. Your choice is part of what you sign."
              : "Compare estimated proceeds, exchange rates, and fees for each option."}
          </p>
        </div>
        <SyntheticChip />
      </div>

      <section className="fx-proceeds-chart card" aria-label="Estimated proceeds comparison">
        <div className="fx-proceeds-chart-head"><div><h3>Estimated payout by option</h3><p>Compare the amount you may receive after fees.</p></div><span>Higher is better</span></div>
        {[...proceedsByCurrency.entries()].map(([currency, routes]) => {
          const max = Math.max(...routes.map((route) => route.net_minor), 1);
          return <div className="fx-proceeds-group" key={currency}>
            {proceedsByCurrency.size > 1 && <div className="fx-proceeds-currency">Payout in {currency}</div>}
            {routes.map((route) => {
              const info = ROUTE_LABELS[route.route_id];
              // only the route that is selected (by default the recommended one) is highlighted
              const isBest = route.route_id === chosenId;
              return <div className="fx-proceeds-row" key={route.route_id}>
                <span className="fx-proceeds-label">{info?.label ?? route.provider}</span>
                <div className="fx-proceeds-track" role="img" aria-label={`${info?.label ?? route.provider}: ${formatMoney(route.net_minor, currency)}`}>
                  <span className={isBest ? "best" : ""} style={{ width: `${Math.max(2, (route.net_minor / max) * 100)}%` }}/>
                </div>
                <strong className={isBest ? "best" : ""}>{formatMoney(route.net_minor, currency)}</strong>
              </div>;
            })}
          </div>;
        })}
      </section>

      {/* 3 Ranked Cards */}
      <div
        className="fx-cards-grid"
        role={onSelectRoute ? "radiogroup" : undefined}
        aria-label={onSelectRoute ? "Payment route to approve" : undefined}
        style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginBottom: 18 }}>
        {sorted.map((route, idx) => {
          const isBest = idx === 0;
          const isChosen = route.route_id === chosenId;
          const info = ROUTE_LABELS[route.route_id] || {
            label: route.provider,
            desc: "Custom trade settlement route",
            icon: ArrowLeftRight,
          };
          const Icon = info.icon;

          return (
            <div
              key={route.route_id}
              className={`fx-route-card ${isChosen ? "is-best-route" : ""}`}
              // Selectable while the deal awaits approval: one click on the card picks it.
              {...(onSelectRoute
                ? {
                    role: "radio",
                    "aria-checked": isChosen,
                    tabIndex: 0,
                    onClick: () => onSelectRoute(isBest ? null : route.route_id),
                    onKeyDown: (e: React.KeyboardEvent) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectRoute(isBest ? null : route.route_id);
                      }
                    },
                  }
                : {})}
              style={{
                cursor: onSelectRoute ? "pointer" : undefined,
                background: "var(--bg-card, #161e29)",
                border: isChosen
                  ? "2px solid var(--accent-cyan, #06b6d4)"
                  : "1px solid var(--border-subtle, #232d3b)",
                borderRadius: "var(--radius, 10px)",
                padding: "16px",
                position: "relative",
                boxShadow: isChosen ? "0 0 16px rgba(6, 182, 212, 0.15)" : undefined,
              }}
            >
              {isBest && (
                <div
                  style={{
                    position: "absolute",
                    top: -10,
                    right: 14,
                    // a plain label when another route is selected: only the selected card is highlighted
                    background: isChosen ? "var(--accent-cyan, #06b6d4)" : "var(--bg-card, #161e29)",
                    color: isChosen ? "#0b0f14" : "var(--text-dim, #94a3b8)",
                    border: isChosen ? "none" : "1px solid var(--border-subtle, #232d3b)",
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
                  {isChosen && <CheckCircle2 size={11} />}
                  <span>Recommended Route</span>
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ color: isChosen ? "var(--accent-cyan, #06b6d4)" : "var(--text-dim, #94a3b8)" }}>
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
                    color: isChosen ? "var(--accent-cyan, #06b6d4)" : "var(--text, #e6ebf2)",
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
                  <span className="muted">Rate difference:</span>
                  <div className="mono tabular" style={{ fontWeight: 600 }}>
                    {(route.spread_bp / 100).toFixed(2)}%
                  </div>
                </div>
              </div>

              <p style={{ margin: 0, fontSize: 11, color: "var(--text-dim, #94a3b8)", lineHeight: 1.35 }}>
                {info.desc}
              </p>

              {onSelectRoute && (
                <div
                  style={{
                    marginTop: 12,
                    fontSize: 12,
                    fontWeight: 600,
                    color: isChosen ? "var(--accent-cyan, #06b6d4)" : "var(--text-dim, #94a3b8)",
                  }}
                >
                  {isChosen ? "✓ Selected for approval" : "Click to select this route"}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Summary Table */}
      <div className="card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>Compare all payment options</h3>
        <table>
          <thead>
            <tr>
              <th>Option</th>
              <th>Provider</th>
              <th>Currencies</th>
              <th className="num">Amount sent</th>
              <th className="num">Fee</th>
              <th className="num">Rate difference</th>
              <th className="num">Net Proceeds</th>
              <th className="num">Rate</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((o, idx) => (
              <tr key={o.route_id} className={o.route_id === chosenId ? "best" : undefined}>
                <td>{ROUTE_LABELS[o.route_id]?.label ?? "Payment option"}</td>
                <td>
                  {o.provider}
                  {o.route_id === chosenId ? (
                    <span className="best-tag">{idx === 0 ? "BEST" : "SELECTED"}</span>
                  ) : (
                    idx === 0 && <span className="muted" style={{ marginLeft: 6, fontSize: 10 }}>RECOMMENDED</span>
                  )}
                </td>
                <td className="mono muted">
                  {o.sell_currency}/{o.buy_currency}
                </td>
                <td className="num tabular">{formatMoney(o.amount_minor, o.sell_currency)}</td>
                <td className="num tabular">{formatMoney(o.fee_minor, o.fee_currency ?? o.buy_currency)}</td>
                <td className="num tabular">{(o.spread_bp / 100).toFixed(2)}%</td>
                <td className="num tabular" style={{ fontWeight: o.route_id === chosenId ? 700 : undefined }}>
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
