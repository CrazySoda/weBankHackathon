import type { FindingStatus, Severity } from "./api";
import {
  ShieldAlert,
  AlertTriangle,
  Info,
  CheckCircle2,
  XCircle,
  AlertOctagon,
  Clock,
  CheckCircle,
  FileMinus,
  FlaskConical,
} from "lucide-react";

/**
 * Format money from integer minor units without float division.
 * Accepts bigint, number, or string.
 * Output format: "${currency} ${whole}${frac}" or "-${currency} ${whole}${frac}"
 */
export function formatMoney(
  minor: bigint | number | string | null | undefined,
  currency: string = "USD",
): string {
  let digits = 2;
  try {
    digits =
      new Intl.NumberFormat("en-US", { style: "currency", currency }).resolvedOptions()
        .maximumFractionDigits ?? 2;
  } catch {
    // Gracefully handle invalid or unrecognized currency codes without throwing
    digits = 2;
  }

  if (minor === null || minor === undefined || minor === "") {
    const frac = digits > 0 ? "." + "0".repeat(digits) : "";
    return `${currency} 0${frac}`;
  }

  let v: bigint;
  try {
    v = BigInt(minor);
  } catch {
    const frac = digits > 0 ? "." + "0".repeat(digits) : "";
    return `${currency} 0${frac}`;
  }

  const neg = v < 0n;
  const s = (neg ? -v : v).toString().padStart(digits + 1, "0");
  const whole = s.slice(0, s.length - digits).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const frac = digits > 0 ? "." + s.slice(-digits) : "";
  return `${neg ? "-" : ""}${currency} ${whole}${frac}`;
}

export function SeverityChip({ severity }: { severity: Severity }) {
  const Icon = severity === "block" ? ShieldAlert : severity === "warn" ? AlertTriangle : Info;
  return (
    <span className={`chip chip-sev-${severity}`}>
      <Icon size={13} aria-hidden="true" />
      <span>{severity === "block" ? "Must fix" : severity === "warn" ? "Review" : "Note"}</span>
    </span>
  );
}

export function StatusChip({ status }: { status: FindingStatus }) {
  const Icon = status === "fixed" ? CheckCircle : status === "waived" ? FileMinus : Clock;
  return (
    <span className={`chip chip-status-${status}`}>
      <Icon size={12} aria-hidden="true" />
      <span>{status === "open" ? "Open" : status === "fixed" ? "Fixed" : "Accepted"}</span>
    </span>
  );
}

export function SyntheticChip() {
  return (
    <span className="chip chip-synthetic" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <FlaskConical size={11} aria-hidden="true" />
      <span>SAMPLE DATA</span>
    </span>
  );
}

export function DecisionChip({ decision }: { decision: string }) {
  const Icon =
    decision === "allow"
      ? CheckCircle2
      : decision === "deny"
        ? XCircle
        : AlertOctagon;
  return (
    <span className={`chip chip-decision-${decision}`}>
      <Icon size={13} aria-hidden="true" />
      <span>{decision === "allow" ? "Ready" : decision === "deny" ? "Not approved" : "Needs review"}</span>
    </span>
  );
}

export function confidenceColor(c: number): string {
  if (c > 0.9) return "var(--status-pass, #10b981)";
  if (c >= 0.7) return "var(--status-warn, #f59e0b)";
  return "var(--status-block, #f43f5e)";
}
