import { AlertOctagon, Inbox, RefreshCw } from "lucide-react";

export function LoadingSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-container" aria-busy="true" aria-label="Loading content">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-card" style={{ height: i === 0 ? 80 : 54 }} />
      ))}
    </div>
  );
}

export function EmptyState({
  title = "No Data Available",
  message = "Upload trade documents or select a 1-click demo scenario to begin.",
  icon: Icon = Inbox,
}: {
  title?: string;
  message?: string;
  icon?: React.ElementType;
}) {
  return (
    <div className="state-empty-card" role="status">
      <div className="empty-icon-box">
        <Icon size={28} />
      </div>
      <h3 style={{ margin: "0 0 6px", fontSize: 15, fontWeight: 600 }}>{title}</h3>
      <p style={{ margin: 0, fontSize: 13, color: "var(--text-dim, #94a3b8)", maxWidth: 360 }}>
        {message}
      </p>
    </div>
  );
}

export function ErrorState({
  title = "Error Loading Data",
  message = "Failed to communicate with the ClearTrade backend service.",
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-error-card" role="alert">
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <AlertOctagon size={20} color="var(--status-block, #f43f5e)" style={{ marginTop: 2 }} />
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "var(--status-block, #f43f5e)" }}>
            {title}
          </h4>
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-dim, #94a3b8)" }}>
            {message}
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="retry-btn"
              style={{
                marginTop: 10,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 12px",
                background: "var(--bg-card, #161e29)",
                border: "1px solid var(--border-subtle, #232d3b)",
                borderRadius: "var(--radius-sm, 6px)",
                color: "var(--text, #e6ebf2)",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              <RefreshCw size={13} />
              <span>Retry</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
