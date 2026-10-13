import type { AuditTrail } from "../api";
import { shortHash } from "../api";

export default function Audit({ audit }: { audit: AuditTrail | undefined }) {
  if (!audit) return <div className="empty">Loading audit trail…</div>;

  return (
    <div>
      <div className={`audit-chain ${audit.chain_ok ? "ok" : "bad"}`}>
        <span
          className="chip"
          style={{
            background: "transparent",
            border: "none",
            color: "inherit",
            fontSize: 14,
          }}
        >
          {audit.chain_ok ? "✓" : "✗"}
        </span>
        {audit.chain_ok
          ? "Audit hash chain verified — every event links to its predecessor."
          : "AUDIT CHAIN BROKEN — events may have been tampered with."}
      </div>

      {audit.events.length === 0 ? (
        <div className="empty">No audit events yet — create and run a deal.</div>
      ) : (
        <div className="card">
          <h2>{audit.events.length} events</h2>
          {audit.events.map((e, i) => (
            <div className="audit-row" key={i}>
              <span className="ts">{e.ts}</span>
              <span className="kind">{e.kind}</span>
              <span className="payload">{JSON.stringify(e.payload)}</span>
              <span className="hash" title={e.hash}>
                {shortHash(e.hash, 10)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
