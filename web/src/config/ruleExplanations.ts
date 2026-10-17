export interface RuleExplanation {
  title: string;
  whatThisMeans: string;
  whatToDoNext: string;
  ruleReference: string;
  jargonTooltip: string;
}

export const RULE_EXPLANATIONS: Record<string, RuleExplanation> = {
  "lc-invoice-exceeds-lc": {
    title: "Invoice Amount Exceeds Letter of Credit",
    whatThisMeans:
      "The total amount on the commercial invoice is higher than the maximum credit amount authorized by the Letter of Credit.",
    whatToDoNext:
      "Upload a corrected commercial invoice matching the LC amount, draw only up to the LC amount, or request an LC amendment from the buyer.",
    ruleReference: "UCP 600 Article 18(b)",
    jargonTooltip:
      "UCP 600 Art. 18(b): a bank may accept an invoice above the LC amount, but only pay up to the LC amount. Many banks still refuse it as a discrepancy.",
  },
  "lc-currency-mismatch": {
    title: "Currency Mismatch Across Documents",
    whatThisMeans:
      "The commercial invoice quotes a currency different from the Letter of Credit.",
    whatToDoNext:
      "Re-issue the commercial invoice in the currency stated in field 32B of the LC.",
    ruleReference: "UCP 600 Article 18(a)(iii)",
    jargonTooltip:
      "Commercial invoices must be made out in the currency of the credit.",
  },
  "lc-beneficiary-mismatch": {
    title: "Beneficiary Entity Name Mismatch",
    whatThisMeans:
      "The exporter entity named on the commercial invoice differs from the beneficiary stipulated in the Letter of Credit.",
    whatToDoNext:
      "Confirm legal entity credentials. Ensure the commercial invoice and transport docs strictly match LC Field 59.",
    ruleReference: "UCP 600 Article 18(a)(i)",
    jargonTooltip:
      "An invoice must appear to have been issued by the beneficiary named in the credit.",
  },
  "lc-applicant-mismatch": {
    title: "Buyer (Applicant) Name Mismatch",
    whatThisMeans:
      "The buyer entity named on the invoice does not match the applicant in LC Field 50.",
    whatToDoNext:
      "Correct the buyer's corporate name and address on the commercial invoice to mirror the LC.",
    ruleReference: "UCP 600 Article 18(a)(ii)",
    jargonTooltip:
      "An invoice must be made out in the name of the applicant.",
  },
  "lc-description-inconsistent": {
    title: "Goods Description Mismatch",
    whatThisMeans:
      "The goods description on the commercial invoice does not correspond with the exact text in LC Field 45A.",
    whatToDoNext:
      "Revise the invoice description to match LC Field 45A verbatim, including model numbers and specifications.",
    ruleReference: "UCP 600 Article 18(c)",
    jargonTooltip:
      "The description of goods in a commercial invoice must correspond with that in the credit.",
  },
  "lc-quantity-mismatch": {
    title: "Quantity Variance Exceeds Tolerance",
    whatThisMeans:
      "The shipped package or goods quantity differs from the LC quantity beyond permissible UCP tolerance.",
    whatToDoNext:
      "Verify packing lists and shipping weight certificates. If partial shipment is prohibited, adjust quantities.",
    ruleReference: "UCP 600 Article 30",
    jargonTooltip:
      "Article 30 governs tolerances in credit amount, quantity, and unit prices (typically 5% unless specified).",
  },
  "ucp600-shipment-after-expiry": {
    title: "Shipment Date is After LC Expiry Date",
    whatThisMeans:
      "Goods were shipped on a date that is past the formal validity period of the Letter of Credit.",
    whatToDoNext:
      "Fatal discrepancy. Request the buyer's issuing bank to amend the LC expiry date (Field 31D).",
    ruleReference: "UCP 600 Article 6(e)",
    jargonTooltip:
      "Documents must be presented on or before the expiry date.",
  },
  "ucp600-shipment-after-latest": {
    title: "Shipment After Latest Permissible Date",
    whatThisMeans:
      "Transport documents indicate a bill of lading date later than LC Field 44C (Latest Date of Shipment).",
    whatToDoNext:
      "Request an LC amendment extending Field 44C from the issuing bank before presenting documents.",
    ruleReference: "UCP 600 Article 14(c)",
    jargonTooltip:
      "Late shipment is a standard discrepancy that permits issuing banks to dishonor presentations.",
  },
  "ucp600-presentation-stale": {
    title: "Presentation Period Exceeded (Stale Documents)",
    whatThisMeans:
      "Documents are presented more than 21 calendar days after the date of shipment.",
    whatToDoNext:
      "Check LC Field 48 for custom presentation periods, or request an extension from the issuing bank.",
    ruleReference: "UCP 600 Article 14(c)",
    jargonTooltip:
      "Unless otherwise agreed, presentation must occur within 21 days after shipment but before expiry.",
  },
  "doc-date-unparseable": {
    title: "Document Date Could Not Be Parsed",
    whatThisMeans:
      "A date field on the trade documents used an unrecognized format or was illegible.",
    whatToDoNext:
      "Ensure all date fields use standard ISO format (YYYY-MM-DD) or DD-MMM-YYYY.",
    ruleReference: "Standard Document Examination",
    jargonTooltip:
      "Dates must be unambiguous to confirm compliance with shipment and presentation deadlines.",
  },
  "sanctions-match": {
    title: "Sanctions Screening Flag",
    whatThisMeans:
      "An entity, vessel, or jurisdiction involved in this trade deal matches a regulatory sanctions watch-list.",
    whatToDoNext:
      "Deal cannot proceed. Escalate to corporate compliance officer for sanctions clearance.",
    ruleReference: "OFAC & International Sanctions Screening",
    jargonTooltip:
      "Banks are prohibited by law from processing trade finance involving sanctioned parties.",
  },
  "vat-refund-estimate": {
    title: "Chinese Export Tax Rebate (VAT Refund)",
    whatThisMeans:
      "Estimated statutory export VAT refund receivable upon customs export declaration confirmation.",
    whatToDoNext:
      "Ensure export customs declaration forms (出口货物报关单) are archived for tax authority filing.",
    ruleReference: "CN State Taxation Administration Export Rebate Regulations",
    jargonTooltip:
      "Chinese micro-exporters can recover up to 13% statutory VAT on eligible manufactured export goods.",
  },
  "injection-hidden-text": {
    title: "Prompt Injection: Hidden Zero-Opacity Text",
    whatThisMeans:
      "Security screener detected hidden or white text embedded within the uploaded PDF file.",
    whatToDoNext:
      "Document rejected as hostile. Re-export clean PDF directly from accounting software without hidden text.",
    ruleReference: "OWASP LLM01 / ClearTrade Security Harness",
    jargonTooltip:
      "Attackers embed hidden text instructions inside trade PDFs to manipulate downstream automated systems.",
  },
  "injection-instruction-phrase": {
    title: "Prompt Injection: Directive Language Detected",
    whatThisMeans:
      "Document text contains adversarial phrases attempting to override automated compliance instructions.",
    whatToDoNext:
      "Upload clean trade documentation. Security harness blocks adversarial prompt injection attempts.",
    ruleReference: "OWASP LLM01 / ClearTrade Security Harness",
    jargonTooltip:
      "Instruction-like phrases (e.g. 'ignore previous rules') are filtered out by security classifiers.",
  },
  "injection-classifier": {
    title: "Hostile Document Injection Flag",
    whatThisMeans:
      "Security classifier model identified high-probability prompt injection payload inside document content.",
    whatToDoNext:
      "Deal escalated to security review. Ensure documents contain only legitimate trade invoice data.",
    ruleReference: "OWASP LLM01 / ClearTrade Security Harness",
    jargonTooltip:
      "Deep semantic classifier verifying untrusted document safety.",
  },
};

export function getRuleExplanation(
  ruleId: string,
  summary?: string,
  explanation?: string,
): RuleExplanation {
  const found = RULE_EXPLANATIONS[ruleId];
  if (found) return found;

  // Generic structured fallback for unknown/custom rule IDs
  return {
    title: summary || `Compliance Rule: ${ruleId}`,
    whatThisMeans:
      explanation ||
      "A regulatory, documentary consistency, or trade finance rule check was flagged for this trade deal.",
    whatToDoNext:
      "Inspect the extracted source document evidence and reconcile discrepancies with your trade counterparty.",
    ruleReference: ruleId,
    jargonTooltip: "Trade documentary examination standard check.",
  };
}
