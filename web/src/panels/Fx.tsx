import type { DealState } from "../api";
import { formatMoney } from "../api";
import { SyntheticChip } from "../ui";

export default function Fx({ state }: { state: DealState }) {
  if (state.fx_options.length === 0) {
    return <div className="empty">No FX quotes yet — run the deal.</div>;
  }

  const bestNet = Math.max(...state.fx_options.map((o) => o.net_minor));
  const opts = [...state.fx_options].sort((a, b) => b.net_minor - a.net_minor);

  return (
    <div className="card">
      <h2>FX route comparison</h2>
      <table>
        <thead>
          <tr>
            <th>Route</th>
            <th>Provider</th>
            <th>Pair</th>
            <th className="num">Amount</th>
            <th className="num">Fee</th>
            <th className="num">Spread</th>
            <th className="num">Net proceeds</th>
            <th className="num">Effective rate</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {opts.map((o) => {
            const isBest = o.net_minor === bestNet;
            return (
              <tr key={o.route_id} className={isBest ? "best" : undefined}>
                <td className="mono">{o.route_id}</td>
                <td>
                  {o.provider}
                  {isBest && <span className="best-tag">BEST</span>}
                </td>
                <td className="mono muted">
                  {o.sell_currency}/{o.buy_currency}
                </td>
                <td className="num">{formatMoney(o.amount_minor, o.sell_currency)}</td>
                <td className="num">{formatMoney(o.fee_minor, o.sell_currency)}</td>
                <td className="num">{o.spread_bp} bp</td>
                <td className="num">{formatMoney(o.net_minor, o.buy_currency)}</td>
                <td className="num">{(o.effective_rate_scaled / 1e6).toFixed(6)}</td>
                <td>{o.synthetic && <SyntheticChip />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>
        Net proceeds and rates are computed by deterministic calculators from sandbox quotes —
        every row is synthetic.
      </p>
    </div>
  );
}
