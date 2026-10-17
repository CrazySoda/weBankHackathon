import type { DealState } from "../api";
import { formatMoney } from "../api";
import CashChart from "../components/CashChart";
import { Calendar, DollarSign, TrendingDown, Clock } from "lucide-react";

export default function CashFlow({ state }: { state: DealState }) {
  const p = state.cash_projection;
  if (!p) {
    return <div className="card empty">No cash projection evaluated yet — run the deal to project cash flow.</div>;
  }

  const isMinNegative = p.min_balance_minor < 0;

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
          <div className="sub">Day {p.min_balance_day} of horizon</div>
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
              <span>Projection Horizon</span>
            </span>
          </div>
          <div className="value tabular">{p.daily_balance_minor.length} days</div>
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
          91-Day Daily Working Capital Projection
        </h3>
        <CashChart projection={p} />
      </div>

      <div className="card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>Scheduled Trade Settlement Events</h3>
        {p.events.length === 0 ? (
          <div className="empty">No cash events recorded in the projection window.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="num">Day</th>
                <th>Event Label</th>
                <th>Classification</th>
                <th className="num">Cash Impact</th>
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
