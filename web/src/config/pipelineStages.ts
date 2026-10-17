export interface NodeConfig {
  id: string;
  label: string;
  description: string;
  isBranch?: boolean; // conditional branch path; styled dashed/muted until visited
}

export interface StageConfig {
  id: string;
  title: string;
  nodes: NodeConfig[];
}

export const PIPELINE_STAGES: StageConfig[] = [
  {
    id: "stage-ingestion",
    title: "1. Intake & Security",
    nodes: [
      {
        id: "intake",
        label: "Intake",
        description: "Validates tenant binding and document content hashes",
      },
      {
        id: "extract_doc",
        label: "Document Extraction",
        description: "Extracts fields and confidence from untrusted PDF text",
      },
      {
        id: "injection_screen",
        label: "Injection Screen",
        description: "Screens for white text and instruction phrases",
      },
    ],
  },
  {
    id: "stage-analysis",
    title: "2. Analysis Engine",
    nodes: [
      {
        id: "plan",
        label: "Planning",
        description: "Selects domain skills under strict allowlists",
      },
      {
        id: "compliance",
        label: "Compliance & UCP 600",
        description: "Checks consistency, sanctions, and CN VAT export refund",
      },
      {
        id: "fx",
        label: "FX Routes",
        description: "Ranks settlement paths by net proceeds and spread",
      },
      {
        id: "cashflow",
        label: "Cash Flow",
        description: "Computes 91-day integer balance series and gap analysis",
      },
    ],
  },
  {
    id: "stage-verification",
    title: "3. Verification",
    nodes: [
      {
        id: "verify",
        label: "Verification",
        description: "Recomputes findings against source documents",
      },
      {
        id: "credit_offer",
        label: "Financing Offer",
        description: "Calculates invoice discounting cost and net advance",
      },
      {
        id: "resolve_exception",
        label: "Exception Resolver",
        description: "Drafts amendment for fixable discrepancies",
        isBranch: true,
      },
      {
        id: "await_corrected_doc",
        label: "Await Corrected Doc",
        description: "Pauses for corrected document upload",
        isBranch: true,
      },
    ],
  },
  {
    id: "stage-policy",
    title: "4. Policy & Human Gate",
    nodes: [
      {
        id: "policy_check",
        label: "Cedar Policy",
        description: "Validates caps, payee match, and block clearance",
      },
      {
        id: "human_approval",
        label: "Human Approval",
        description: "Verifies Ed25519 signature over canonical deal hash",
      },
      {
        id: "escalate",
        label: "Escalation",
        description: "Terminal stop on fatal errors or unfixable discrepancies",
        isBranch: true,
      },
    ],
  },
  {
    id: "stage-settlement",
    title: "5. Settlement & Audit",
    nodes: [
      {
        id: "execute",
        label: "Sandbox Payout",
        description: "Executes idempotent sandbox payout with nonce lock",
      },
      {
        id: "report",
        label: "Audit Anchoring",
        description: "Anchors SHA-256 hash chain and outputs receipt",
      },
    ],
  },
];
