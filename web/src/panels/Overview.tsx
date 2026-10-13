import type { DealState } from "../api";
import { formatMoney } from "../api";
import { DecisionChip, SeverityChip, StatusChip } from "../ui";

export default function Overview({ state }: { state: DealState }) {
  const open = state.findings.filter((f) => f.status === "open");
  const blocks = open.filter((f) => f.severity === "block");
  const warns = open.filter((f) => f.severity === "warn");
  const waivers = state.findings.filter((f) => f.status === "waived");

  const payee = findPayee(state);
  const amount = findAmount(state);

  return (
    <div>
      <div className="card-grid">
        <Stat label="Documents" value={String(state.documents.length)} sub={`${state.extracted.length} extracted`} />
        <Stat label="Open findings" value={String(open.length)} sub={`${blocks.length} block · ${warns.length} warn`} />
        <Stat label="Waivers" value={String(waivers.length)} sub="named human required" />
        <Stat
          label="FX routes"
          value={String(state.fx_options.length)}
          sub={bestRoute(state) ? `best: ${bestRoute(state)!.provider}` : "no quotes"}
        />
        <Stat
          label="Deal amount"
          value={amount !== null ? formatMoney(amount, "USD") : "—"}
          sub={payee ? `payee: ${payee}` : "payee unknown"}
        />
      </div>

      <div className="card">
        <h2>Policy decision</h2>
        {state.policy ? (
          <>
            <div className="row" style={{ marginBottom: 10 }}>
              <DecisionChip decision={state.policy.decision} />
              <span className="muted">
                engine <span className="mono">{state.policy.engine}</span>
              </span>
            </div>
            {state.policy.reason && <p className="muted" style={{ marginTop: 0 }}>{state.policy.reason}</p>}
            {state.policy.rules.length > 0 && (
              <table>
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Result</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {state.policy.rules.map((r) => (
                    <tr key={r.rule}>
                      <td className="mono">{r.rule}</td>
                      <td>
                        <span className={`chip ${r.allowed ? "chip-decision-allow" : "chip-sev-block"}`}>
                          {r.allowed ? "pass" : "fail"}
                        </span>
                      </td>
                      <td className="muted">{r.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <div className="empty">No policy decision yet — run the deal.</div>
        )}
      </div>

      {state.receipt && (
        <div className="card">
          <h2>Receipt</h2>
          <dl className="kv">
            <dt>Receipt ID</dt>
            <dd>{state.receipt.receipt_id}</dd>
            <dt>Payout reference</dt>
            <dd>{state.receipt.payout_ref}</dd>
            <dt>Amount</dt>
            <dd>{formatMoney(state.receipt.amount.amount_minor, state.receipt.amount.currency)}</dd>
            <dt>Anchored hash</dt>
            <dd>{state.receipt.anchored_hash ?? "—"}</dd>
            <dt>Executed at</dt>
            <dd>{state.receipt.executed_at}</dd>
          </dl>
        </div>
      )}

      {state.escalation_reason && (
        <div className="card" style={{ borderColor: "#7f1d1d" }}>
          <h2 style={{ color: "#fca5a5" }}>Escalated</h2>
          <p style={{ margin: 0, color: "#fca5a5" }}>{state.escalation_reason}</p>
          {state.fatal_error && (
            <p className="mono muted" style={{ marginBottom: 0 }}>{state.fatal_error}</p>
          )}
        </div>
      )}

      {state.injection_flags.length > 0 && (
        <div className="card">
          <h2>Injection screening</h2>
          {state.injection_flags.map((f, i) => (
            <div key={i} className={`finding sev-${f.severity}`}>
              <div className="finding-head">
                <SeverityChip severity={f.severity} />
                <span className="finding-rule">{f.kind}</span>
                <span className="mono faint">{f.doc_id}</span>
              </div>
              <div className="finding-explanation">{f.detail}</div>
              {f.evidence.map((e, j) => (
                <div key={j} className="evidence">
                  <div className="quote">{e.snippet}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {state.approval && (
        <div className="card">
          <h2>Approval <StatusChip status="fixed" /></h2>
          <dl className="kv">
            <dt>Approver</dt>
            <dd>{state.approval.approver_id}</dd>
            <dt>Method</dt>
            <dd>{state.approval.method}</dd>
            <dt>Deal hash</dt>
            <dd>{state.approval.deal_hash}</dd>
            <dt>Signed at</dt>
            <dd>{state.approval.signed_at}</dd>
            <dt>Nonce</dt>
            <dd>{state.approval.nonce}</dd>
          </dl>
        </div>
      )}

      {state.served_by.length > 0 && (
        <div className="card">
          <h2>Model usage</h2>
          <table>
            <thead>
              <tr>
                <th>Node</th>
                <th>Alias</th>
                <th>Deployment</th>
                <th className="num">Tokens</th>
                <th className="num">Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              {state.served_by.map((m, i) => (
                <tr key={i}>
                  <td className="mono">{m.node}</td>
                  <td className="mono">{m.alias}</td>
                  <td className="mono muted">
                    {m.deployment} {m.degraded ? "(degraded)" : ""}
                  </td>
                  <td className="num">{m.prompt_tokens + m.completion_tokens}</td>
                  <td className="num">{formatMoney(m.cost_minor, "USD")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SyntheticNote />
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function SyntheticNote() {
  return (
    <p className="faint" style={{ fontSize: 12 }}>
      All amounts, FX quotes and finance offers in this console are synthetic data
      generated for the demo — no real counterparties or payments.
    </p>
  );
}

export function findPayee(state: DealState): string | null {
  for (const d of state.extracted) {
    if (d.kind !== "commercial_invoice") continue;
    const b = d.fields.find((f) => f.name === "beneficiary");
    if (b && b.value !== null && b.value !== undefined) return String(b.value);
  }
  return null;
}

export function findAmount(state: DealState): number | null {
  for (const d of state.extracted) {
    if (d.kind !== "commercial_invoice") continue;
    const a = d.fields.find((f) => f.name === "total_amount_minor" || f.name === "amount_minor");
    if (a && typeof a.value === "number") return a.value;
  }
  return null;
}

export function bestRoute(state: DealState) {
  if (state.fx_options.length === 0) return null;
  return state.fx_options.reduce((a, b) => (b.net_minor > a.net_minor ? b : a));
}

export function totalAmountOf(state: DealState): number | null {
  const amount = findAmount(state);
  if (amount !== null) return amount;
  if (state.finance_offer) return state.finance_offer.face.amount_minor;
  const fx = bestRoute(state);
  return fx ? fx.amount_minor : null;
}