import type { FindingStatus, Severity } from "./api";

export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span className={`chip chip-sev-${severity}`}>
      <span className="dot" />
      {severity}
    </span>
  );
}

export function StatusChip({ status }: { status: FindingStatus }) {
  return <span className={`chip chip-status-${status}`}>{status}</span>;
}

export function SyntheticChip() {
  return <span className="chip chip-synthetic">synthetic</span>;
}

export function DecisionChip({ decision }: { decision: string }) {
  return <span className={`chip chip-decision-${decision}`}>{decision}</span>;
}

export function confidenceColor(c: number): string {
  if (c >= 0.85) return "#34d399";
  if (c >= 0.6) return "#fbbf24";
  return "#f87171";
}

/** Clean, compact y-axis tick label for money minor units. */
export function compactMoney(minor: number, currency = "$"): string {
  const units = minor / 100;
  const abs = Math.abs(units);
  const sign = units < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}${currency}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}${currency}${(abs / 1_000).toFixed(1)}K`;
  return `${sign}${currency}${abs.toFixed(0)}`;
}
