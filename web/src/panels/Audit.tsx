import { useState } from "react";
import type { AuditTrail, DealState } from "../api";
import { shortHash } from "../api";
import { DecisionChip } from "../ui";
import {
  Activity,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Copy,
  FileCheck2,
  FilePlus2,
  FileX2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

export default function Audit({ audit, state }: { audit: AuditTrail | undefined; state?: DealState | null }) {
  const [expandedHash, setExpandedHash] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  if (!audit) {
    return <div className="review-history-loading" role="status"><Activity size={18}/>Loading deal history…</div>;
  }

  const copyHash = async (hash: string) => {
    try {
      await navigator.clipboard.writeText(hash);
      setCopiedHash(hash);
      window.setTimeout(() => setCopiedHash(null), 1500);
    } catch {
      // Clipboard access is optional; the history remains readable without it.
    }
  };

  return <div className="review-history">
    <section className={`history-integrity ${audit.chain_ok ? "verified" : "attention"}`}>
      <span className="history-integrity-icon">{audit.chain_ok ? <ShieldCheck size={21}/> : <ShieldAlert size={21}/>}</span>
      <div><strong>{audit.chain_ok ? "Review history verified" : "Review history needs attention"}</strong>
        <p>{audit.chain_ok
          ? `All ${audit.events.length} saved records are linked in order. We found no changes to the history.`
          : "Some saved records could not be verified. Treat this history as incomplete."}</p>
      </div>
      <span className="history-integrity-badge">{audit.chain_ok ? "Verified" : "Check needed"}</span>
    </section>

    {audit.events.length === 0 ? <section className="history-empty-state">
      <span><ClipboardCheck size={22}/></span>
      <div><strong>Your deal history will appear here</strong><p>Add documents or start a review to see the actions and decisions for this deal.</p></div>
    </section> : <section className="history-activity-card">
      <header><div><span className="history-section-icon"><Activity size={16}/></span><div><h2>Deal activity</h2><p>Important actions and review steps, in order.</p></div></div><span className="history-count">{audit.events.length} records</span></header>
      <div className="history-timeline">
        {[...audit.events].reverse().map((event) => {
          const expanded = expandedHash === event.hash;
          return <article className="history-event" key={event.hash}>
            <button type="button" className="history-event-toggle" aria-expanded={expanded} onClick={() => setExpandedHash(expanded ? null : event.hash)}>
              <span className="history-event-icon">{eventIcon(event.kind)}</span>
              <span className="history-event-copy"><strong>{eventTitle(event.kind)}</strong><small>{eventDescription(event.kind, event.payload)}</small></span>
              <time>{formatTimestamp(event.ts)}</time>
              <span className="history-event-chevron">{expanded ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}</span>
            </button>
            {expanded && <details className="history-technical-details">
              <summary>Technical verification details</summary>
              <div className="history-fingerprint"><span>Record fingerprint</span><button type="button" onClick={() => void copyHash(event.hash)} title="Copy full verification code"><code>{shortHash(event.hash, 12)}</code>{copiedHash === event.hash ? <Check size={13}/> : <Copy size={13}/>}</button></div>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </details>}
          </article>;
        })}
      </div>
    </section>}

    {state?.policy && <section className="history-policy-card">
      <header><span className="history-section-icon"><FileCheck2 size={16}/></span><div><h2>Approval checks</h2><p>Requirements checked before this deal can move forward.</p></div><DecisionChip decision={state.policy.decision}/></header>
      {state.policy.rules.length > 0 && <ul>{state.policy.rules.map((rule) => <li key={rule.rule}>
        <span className={rule.allowed ? "policy-pass" : "policy-fail"}>{rule.allowed ? <CheckCircle2 size={15}/> : <ShieldAlert size={15}/>}</span>
        <span><strong>{humanizeRule(rule.rule)}</strong><small>{rule.detail}</small></span>
      </li>)}</ul>}
    </section>}
  </div>;
}

function eventIcon(kind: string) {
  if (kind === "document_registered") return <FilePlus2 size={16}/>;
  if (kind === "document_removed") return <FileX2 size={16}/>;
  if (kind === "node_finished" || kind === "deal_created") return <CheckCircle2 size={16}/>;
  if (kind === "node_failed" || kind === "budget_exceeded" || kind === "tool_refused") return <ShieldAlert size={16}/>;
  return <Activity size={16}/>;
}

function eventTitle(kind: string): string {
  const titles: Record<string, string> = {
    deal_created: "Deal created",
    document_registered: "Document added",
    document_removed: "Document removed",
    copilot_asked: "Deal assistant used",
    node_started: "Review step started",
    node_finished: "Review step completed",
    node_interrupted: "Review paused for your input",
    node_failed: "Review step needs attention",
    budget_exceeded: "Review paused",
    tool_refused: "Action blocked for safety",
  };
  return titles[kind] ?? "Deal update";
}

function eventDescription(kind: string, payload: Record<string, unknown>): string {
  if (kind === "document_registered") return `${String(payload.filename ?? "A document")} was added to this deal.`;
  if (kind === "document_removed") return "A document was removed from this deal.";
  if (kind === "copilot_asked") return "You asked the deal assistant a question.";
  if (kind === "deal_created") return "A workspace was opened for this trade.";
  if (kind === "node_started" || kind === "node_finished") {
    const node = humanizeNode(String(payload.node ?? "review"));
    return kind === "node_started" ? `${node} is underway.` : `${node} is complete.`;
  }
  if (kind === "node_interrupted") return "The review is waiting for information or a decision from you.";
  if (kind === "node_failed") return "A review step could not finish. Check the Summary for the next step.";
  if (kind === "budget_exceeded") return "The review stopped before it could finish. Try again or contact your administrator.";
  if (kind === "tool_refused") return "A requested action was stopped by a safety check.";
  return "This action was saved to the deal history.";
}

function humanizeNode(node: string): string {
  const labels: Record<string, string> = {
    intake: "Preparing documents",
    extract_doc: "Reading a document",
    injection_screen: "Checking document safety",
    plan: "Preparing the review",
    compliance: "Checking trade requirements",
    fx: "Comparing payment routes",
    cashflow: "Building the cash forecast",
    verify: "Cross-checking deal details",
    resolve_exception: "Reviewing a discrepancy",
    await_corrected_doc: "Waiting for a corrected document",
    credit_offer: "Checking financing options",
    policy_check: "Checking approval requirements",
    human_approval: "Requesting approval",
    execute: "Processing the demo payment",
    escalate: "Preparing next steps",
    report: "Preparing your summary",
  };
  return labels[node] ?? "Reviewing the deal";
}

function humanizeRule(rule: string): string {
  return rule.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
