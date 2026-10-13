import type { StreamEvent } from "../api";

/** Live SSE activity ticker: node_started / node_finished / interrupt / done / error. */
export default function Ticker({
  events,
  running,
}: {
  events: StreamEvent[];
  running: boolean;
}) {
  const shown = events.slice(-100);

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 13,
            color: "#94a3b8",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          Live activity
        </h2>
        {running ? (
          <span className="live-dot">streaming</span>
        ) : (
          <span className="faint" style={{ fontSize: 12 }}>
            idle
          </span>
        )}
      </div>
      <div className="ticker" aria-live="polite">
        {shown.length === 0 ? (
          <span className="faint">No stream events yet — press “Run deal”.</span>
        ) : (
          shown.map((e, i) => (
            <div
              key={i}
              className={`ticker-line ${
                e.type === "done" ? "ev-done" : e.type === "error" ? "ev-error" : ""
              }`}
            >
              <span className="ev ts">{(e.ts ?? "").slice(11, 19)}</span>
              <span className="ev">{e.type}</span>
              <span>{e.node || e.detail || ""}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
