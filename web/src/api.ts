/**
 * Typed API client for the ClearTrade backend (BUILD_PLAN M7).
 * All requests use the /api prefix; vite (dev) and nginx (container) proxy it
 * to the FastAPI backend. Money is integer minor units everywhere.
 */

const BASE = "/api";

export type DocKind =
  | "letter_of_credit"
  | "commercial_invoice"
  | "packing_list"
  | "bill_of_lading"
  | "presentation_schedule"
  | "unknown";

export type Severity = "info" | "warn" | "block";
export type FindingStatus = "open" | "fixed" | "waived";

export interface Money {
  minor: number;
  currency: string;
}

export interface SourceRef {
  page?: number | null;
  bbox?: [number, number, number, number] | null;
  text_span?: [number, number] | null;
  snippet: string;
}

export interface DocRef {
  doc_id: string;
  deal_id: string;
  kind: DocKind;
  sha256: string;
  filename: string;
  mime: string;
  size_bytes: number;
}

export interface ExtractedField {
  name: string;
  value: unknown;
  confidence: number;
  source: SourceRef;
}

export interface ExtractedDoc {
  doc_id: string;
  sha256: string;
  kind: DocKind;
  fields: ExtractedField[];
  extraction_model: string;
  low_confidence: boolean;
}

export interface Flag {
  kind:
    | "instruction_like_phrase"
    | "hidden_text"
    | "beneficiary_change_language"
    | "metadata_anomaly"
    | "classifier_hit";
  severity: Severity;
  doc_id: string;
  evidence: SourceRef[];
  detail: string;
}

export interface EvidenceRef {
  doc_id: string;
  source: SourceRef;
  quote: string;
}

export interface Finding {
  check_id: string;
  rule_id: string;
  severity: Severity;
  status: FindingStatus;
  fixable: boolean;
  summary: string;
  explanation: string;
  evidence: EvidenceRef[];
}

export interface FxOption {
  route_id: string;
  provider: string;
  synthetic: boolean;
  sell_currency: string;
  buy_currency: string;
  amount_minor: number;
  net_minor: number;
  effective_rate_scaled: number;
  spread_bp: number;
  fee_minor: number;
  fee_currency?: string | null;
}

export interface CashEventState {
  day: number;
  amount_minor: number;
  currency: string;
  label: string;
  source: string;
}

export interface CashProjectionState {
  currency: string;
  opening_balance_minor: number;
  daily_balance_minor: number[];
  min_balance_minor: number;
  min_balance_day: number;
  days_below_zero: number;
  events: CashEventState[];
}

export interface FinanceOfferState {
  provider: string;
  face: Money;
  advance: Money;
  total_cost: Money;
  net_proceeds: Money;
  effective_cost_bp_annual: number;
  days_to_maturity: number;
  synthetic: boolean;
}

export interface PolicyRuleResult {
  rule: string;
  allowed: boolean;
  detail: string;
}

export interface PolicyDecision {
  decision: "allow" | "deny" | "escalate";
  engine: string;
  rules: PolicyRuleResult[];
  reason: string;
}

export interface SignedApproval {
  deal_hash: string;
  approver_id: string;
  method: "webauthn_passkey" | "wechat_soter" | "pin_otp" | "demo_key";
  signature_b64: string;
  signed_at: string;
  nonce: string;
}

export interface Receipt {
  receipt_id: string;
  deal_id: string;
  payout_ref: string;
  amount: Money;
  anchored_hash?: string | null;
  anchor_tx?: string | null;
  executed_at: string;
}

export interface ModelUse {
  node: string;
  alias: string;
  deployment: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_minor: number;
  degraded: boolean;
  prompt_version: string;
}

export interface CheckPlan {
  plan_id: string;
  chosen_skills: string[];
  checks: string[];
  rationale: string;
}

export interface DealState {
  deal_id: string;
  tenant_id: string;
  documents: DocRef[];
  extracted: ExtractedDoc[];
  injection_flags: Flag[];
  check_plan: CheckPlan | null;
  findings: Finding[];
  fx_options: FxOption[];
  selected_fx_route?: string | null;
  cash_projection: CashProjectionState | null;
  verified: Finding[];
  amendment_draft: string | null;
  resolve_attempts: number;
  finance_offer: FinanceOfferState | null;
  policy: PolicyDecision | null;
  approval: SignedApproval | null;
  receipt: Receipt | null;
  served_by: ModelUse[];
  fatal_error: string | null;
  escalation_reason: string | null;
  report_summary: string | null;
  pending_doc: DocRef | null;
}

export interface DealDetail {
  state: DealState;
  running: boolean;
  synthetic_data: boolean;
}

export interface AuditEventRow {
  kind: string;
  payload: Record<string, unknown>;
  ts: string;
  hash: string;
}

export interface AuditTrail {
  events: AuditEventRow[];
  chain_ok: boolean;
  synthetic_data: boolean;
}

/** Subset of the interrupt payload the nodes attach via langgraph interrupt(). */
export interface ApprovalInterruptPayload {
  kind: "human_approval";
  deal_id: string;
  findings: Finding[];
  waivers: Finding[];
  /** Signed as part of the approval render: the approver must see these. */
  injection_flags: Flag[];
  fx_options: FxOption[];
  finance_offer: FinanceOfferState | null;
  payee: string | null;
  applicant: string | null;
  amount_minor: number | null;
  policy: PolicyDecision | null;
}

export interface CorrectedDocInterruptPayload {
  kind: "await_corrected_doc";
  amendment_draft: string | null;
  open_block_findings: Array<{ rule_id: string; summary: string }>;
}

export interface SyntheticBadge {
  synthetic_data: boolean;
}

export interface InterruptPayload {
  kind: string;
  [key: string]: unknown;
}

export type StreamEvent = {
  type:
    | "node_started"
    | "node_finished"
    | "node_interrupted"
    | "interrupt"
    | "deal_created"
    | "document_registered"
    | "done"
    | "error"
    | string;
  node?: string;
  ts?: string;
  state?: DealState;
  detail?: string;
  payload?: InterruptPayload;
};

export type CopilotCardKind = "findings" | "fx" | "cash" | "documents" | "none";

export interface CopilotQuestion {
  question: string;
  history: Array<{ role: "user" | "assistant"; text: string }>;
  focus_check_id?: string | null;
}

export interface CopilotReply extends SyntheticBadge {
  answer: string;
  card: CopilotCardKind;
  finding_ids: string[];
  follow_ups: string[];
  declined: boolean;
  model: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; env: string } & SyntheticBadge>("/health"),

  createDeal: () =>
    request<{ deal_id: string } & SyntheticBadge>("/deals", {
      method: "POST",
    }),

  loadSeedDeal: (seedId: string) =>
    request<{ deal_id: string; seed_id: string } & SyntheticBadge>(`/deals/seed/${encodeURIComponent(seedId)}`, {
      method: "POST",
    }),

  askCopilot: (dealId: string, body: CopilotQuestion) =>
    request<CopilotReply>(`/deals/${encodeURIComponent(dealId)}/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  uploadDocument: (dealId: string, file: File, kind: DocKind) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<{ doc_id: string; sha256: string } & SyntheticBadge>(
      `/deals/${encodeURIComponent(dealId)}/documents`,
      { method: "POST", body: form },
    );
  },

  removeDocument: (dealId: string, docId: string) =>
    request<{ removed: boolean; doc_id: string } & SyntheticBadge>(
      `/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(docId)}`,
      { method: "DELETE" },
    ),

  runDeal: (dealId: string) =>
    request<{ started: boolean; stream: string } & SyntheticBadge>(
      `/deals/${encodeURIComponent(dealId)}/run`,
      { method: "POST" },
    ),

  checkReadiness: (dealId: string) =>
    request<DealDetail>(`/deals/${encodeURIComponent(dealId)}/readiness`, { method: "POST" }),

  getDeal: (dealId: string) =>
    request<DealDetail>(`/deals/${encodeURIComponent(dealId)}`),

  // fxRoute: the route the approver chose; it is part of what gets signed.
  signDemo: (dealId: string, fxRoute?: string) =>
    request<{ approval: SignedApproval; demo_shortcut: boolean; notice: string } & SyntheticBadge>(
      `/deals/${encodeURIComponent(dealId)}/sign_demo`, {
      method: "POST",
      ...(fxRoute
        ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fx_route: fxRoute }) }
        : {}),
    }),

  resume: (
    dealId: string,
    body: { action: string; approval?: SignedApproval; note?: string; fx_route?: string },
  ) =>
    request<{ resumed: boolean } & SyntheticBadge>(`/deals/${encodeURIComponent(dealId)}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  demoSeed: (scenario: "clean" | "discrepancy" | "mismatch" | "injection") =>
    request<{ deal_id: string; scenario: string } & SyntheticBadge>(
      `/deals/demo-seed/${encodeURIComponent(scenario)}`,
      { method: "POST" },
    ),

  audit: (dealId: string) =>
    request<AuditTrail>(`/deals/${encodeURIComponent(dealId)}/audit`),
};

export { formatMoney } from "./ui";

/** Shorten a long hash for display. */
export function shortHash(hash: string | null | undefined, n = 10): string {
  if (!hash) return "—";
  return hash.length <= n ? hash : `${hash.slice(0, n)}…`;
}
