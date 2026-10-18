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
    title: "Documents",
    nodes: [
      {
        id: "intake",
        label: "Add documents",
        description: "Checks your files before review",
      },
      {
        id: "extract_doc",
        label: "Read details",
        description: "Finds key details in each document",
      },
      {
        id: "injection_screen",
        label: "Check document safety",
        description: "Looks for suspicious content",
      },
    ],
  },
  {
    id: "stage-analysis",
    title: "Trade checks",
    nodes: [
      {
        id: "plan",
        label: "Choose checks",
        description: "Selects the checks needed for this deal",
      },
      {
        id: "compliance",
        label: "Check trade terms",
        description: "Compares the documents and key trade details",
      },
      {
        id: "fx",
        label: "FX Routes",
        description: "Ranks settlement paths by net proceeds and spread",
      },
      {
        id: "cashflow",
        label: "Cash Flow",
        description: "Projects daily balances from day 0 through day 90",
      },
    ],
  },
  {
    id: "stage-verification",
    title: "Money & timing",
    nodes: [
      {
        id: "verify",
        label: "Verify the details",
        description: "Checks each issue against the source documents",
      },
      {
        id: "credit_offer",
        label: "Review financing",
        description: "Estimates available financing and its cost",
      },
      {
        id: "resolve_exception",
        label: "Prepare a suggested fix",
        description: "Drafts a suggested change for correctable issues",
        isBranch: true,
      },
      {
        id: "await_corrected_doc",
        label: "Waiting for your update",
        description: "Pauses until you add an updated document",
        isBranch: true,
      },
    ],
  },
  {
    id: "stage-policy",
    title: "Your decision",
    nodes: [
      {
        id: "policy_check",
        label: "Check approval details",
        description: "Checks the amount, recipient, and open issues",
      },
      {
        id: "human_approval",
        label: "Your approval",
        description: "Waits for you to approve or decline",
      },
      {
        id: "escalate",
        label: "Needs a closer look",
        description: "Pauses when an issue needs human attention",
        isBranch: true,
      },
    ],
  },
  {
    id: "stage-settlement",
    title: "Complete",
    nodes: [
      {
        id: "execute",
        label: "Test payment",
        description: "Completes the sample payment",
      },
      {
        id: "report",
        label: "Save your receipt",
        description: "Creates a receipt and saves the review record",
      },
    ],
  },
];
