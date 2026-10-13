import type { DealState } from "../api";
import { formatMoney } from "../api";
import CashChart from "../components/CashChart";

export default function CashFlow({ state }: { state: DealState }) {
  const p = state.cash_projection;
  if (!p) {
    return <div className="empty">No cash projection yet — run the deal.</div>;
  }

  return (
    <div>
      <div className="card-grid">
        <div className="stat">
          <div className="label">Opening balance</div>
          <div className="value">{formatMoney(p.opening_balance_minor, p.currency)}</div>
        </div>
        <div className="stat">
          <div className="label">Minimum balance</div>
          <div className="value" style={{ color: p.min_balance_minor < 0 ? "#f87171" : undefined }}>
            {formatMoney(p.min_balance_minor, p.currency)}
          </div>
          <div className="sub">day {p.min_balance_day}</div>
        </div>
        <div className="stat">
          <div className="label">Days below zero</div>
          <div className="value" style={{ color: p.days_below_zero > 0 ? "#f87171" : undefined }}>
            {p.days_below_zero}
          </div>
          <div className="sub">gap financing may be needed</div>
        </div>
        <div className="stat">
          <div className="label">Horizon</div>
          <div className="value">{p.daily_balance_minor.length} days</div>
          <div className="sub">{p.currency}</div>
        </div>
      </div>

      <div className="chart-wrap">
        <h2 style={{ margin: "0 0 8px", fontSize: 13, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Projected daily cash balance
        </h2>
        <CashChart projection={p} />
      </div>

      <div className="card">
        <h2>Cash events</h2>
        {p.events.length === 0 ? (
          <div className="empty">No cash events in the projection window.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="num">Day</th>
                <th>Label</th>
                <th>Source</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {[...p.events]
                .sort((a, b) => a.day - b.day)
                .map((e, i) => (
                  <tr key={i}>
                    <td className="num">{e.day}</td>
                    <td>{e.label}</td>
                    <td className="mono muted">{e.source}</td>
                    <td className="num" style={{ color: e.amount_minor < 0 ? "#f87171" : "#34d399" }}>
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
