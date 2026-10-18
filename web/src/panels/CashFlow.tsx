import type { DealState } from "../api";
import { formatMoney } from "../api";
import CashChart from "../components/CashChart";
import { Calendar, DollarSign, TrendingDown, Clock, WalletCards } from "lucide-react";
import GuidedEmptyState from "../components/GuidedEmptyState";

export default function CashFlow({ state, onRunReview, onAddDocuments }: { state: DealState; onRunReview?: () => void; onAddDocuments?: () => void }) {
  const p = state.cash_projection;
  if (!p) {
    const hasDocuments = state.documents.length > 0;
    return <GuidedEmptyState
      icon={WalletCards}
      eyebrow="Cash forecast"
      title={hasDocuments ? "See how this deal affects cash" : "Build your cash forecast"}
      description={hasDocuments
        ? "Review the trade documents to estimate when money may leave and arrive, and spot any projected shortfall."
        : "Add the deal documents first. ClearTrade will use their payment details to create an illustrative forecast."}
      actionLabel={hasDocuments ? "Run deal review" : "Add documents"}
      onAction={hasDocuments ? onRunReview : onAddDocuments}
      steps={["Read payment terms", "Map expected cash dates", "See possible shortfalls"]}
      footnote="Forecasts are estimates, not a live bank balance."
    />;
  }

  const isMinNegative = p.min_balance_minor < 0;
  const horizonDays = Math.max(0, p.daily_balance_minor.length - 1);

  return (
    <div>
      <div className="card-grid">
        <div className="stat">
          <div className="label">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <DollarSign size={13} color="var(--text-dim, #94a3b8)" />
              <span>Opening balance</span>
            </span>
          </div>
          <div className="value tabular">{formatMoney(p.opening_balance_minor, p.currency)}</div>
        </div>

        <div className="stat">
          <div className="label">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <TrendingDown size={13} color={isMinNegative ? "var(--status-block, #f43f5e)" : "var(--text-dim, #94a3b8)"} />
              <span>Minimum balance</span>
            </span>
          </div>
          <div
            className="value tabular"
            style={{ color: isMinNegative ? "var(--status-block, #f43f5e)" : undefined }}
          >
            {formatMoney(p.min_balance_minor, p.currency)}
          </div>
          <div className="sub">{p.min_balance_day === 0 ? "At the start" : `Day ${p.min_balance_day} of forecast`}</div>
        </div>

        <div className="stat">
          <div className="label">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Clock size={13} color={p.days_below_zero > 0 ? "var(--status-block, #f43f5e)" : "var(--text-dim, #94a3b8)"} />
              <span>Days below zero</span>
            </span>
          </div>
          <div
            className="value tabular"
            style={{ color: p.days_below_zero > 0 ? "var(--status-block, #f43f5e)" : undefined }}
          >
            {p.days_below_zero}
          </div>
          <div className="sub">{p.days_below_zero > 0 ? "Gap financing recommended" : "Surplus maintained"}</div>
        </div>

        <div className="stat">
          <div className="label">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Calendar size={13} color="var(--text-dim, #94a3b8)" />
              <span>Forecast period</span>
            </span>
          </div>
          <div className="value tabular">{horizonDays} days</div>
          <div className="sub">{p.currency} denomination</div>
        </div>
      </div>

      <div className="chart-wrap card" style={{ marginBottom: 16 }}>
        <h3
          style={{
            margin: "0 0 12px",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "0.04em",
          }}
        >
          {horizonDays}-Day Cash Flow Projection
        </h3>
        <CashChart projection={p} />
        <p className="faint" style={{ margin: "12px 0 0", fontSize: 12 }}>
          Illustrative estimate: assumes a zero opening balance, a 30% deposit on day 0, and the LC amount received at maturity. It does not use a bank account balance.
        </p>
      </div>

      <div className="card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>Expected cash movements</h3>
        {p.events.length === 0 ? (
          <div className="cash-events-empty"><Calendar size={18}/><div><strong>No dated payments in this forecast</strong><span>Add documents with payment dates to see when cash may move.</span></div></div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="num">Day</th>
                <th>Payment</th>
                <th>Type</th>
                <th className="num">Expected change</th>
              </tr>
            </thead>
            <tbody>
              {[...p.events]
                .sort((a, b) => a.day - b.day)
                .map((e, i) => (
                  <tr key={i}>
                    <td className="num mono tabular">Day {e.day}</td>
                    <td style={{ fontWeight: 600 }}>{e.label}</td>
                    <td className="mono muted">{e.source}</td>
                    <td
                      className="num mono tabular"
                      style={{
                        fontWeight: 700,
                        color:
                          e.amount_minor < 0
                            ? "var(--status-block, #f43f5e)"
                            : "var(--status-pass, #10b981)",
                      }}
                    >
                      {formatMoney(e.amount_minor, e.currency)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
