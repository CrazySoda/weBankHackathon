import type { DealState, DocKind, ExtractedDoc, ExtractedField } from "./api";

export interface CoreDocumentRequirement {
  kind: Exclude<DocKind, "unknown">;
  label: string;
  details: string;
  requiredFields: string[][];
}

export const CORE_DOCUMENTS: CoreDocumentRequirement[] = [
  {
    kind: "letter_of_credit",
    label: "Letter of credit",
    details: "Buyer, seller, amount and payment terms",
    requiredFields: [["applicant", "buyer"], ["beneficiary", "seller"], ["lc_amount", "amount", "total_amount"]],
  },
  {
    kind: "commercial_invoice",
    label: "Commercial invoice",
    details: "Invoice amount and seller",
    requiredFields: [["total_amount", "total_amount_minor", "amount", "amount_minor"], ["beneficiary", "seller"]],
  },
  {
    kind: "packing_list",
    label: "Packing list",
    details: "Goods quantity and package or weight details",
    requiredFields: [["quantity", "goods_quantity"], ["total_packages", "package_count", "number_of_packages", "gross_weight_kg", "net_weight_kg"]],
  },
];

export type DocumentReadiness = {
  requirement: CoreDocumentRequirement;
  uploaded: boolean;
  status: "missing" | "uploaded" | "ready" | "review";
  message: string;
};

export function documentReadiness(state: DealState | null): DocumentReadiness[] {
  const uploadOrder = new Map(state?.documents.map((doc, index) => [doc.doc_id, index]) ?? []);
  return CORE_DOCUMENTS.map((requirement): DocumentReadiness => {
    if (!state) return { requirement, uploaded: false, status: "missing", message: "Select a deal" };

    const candidates: ExtractedDoc[] = state.extracted
      .filter((doc) => doc.kind === requirement.kind)
      .sort((a, b) => (uploadOrder.get(a.doc_id) ?? -1) - (uploadOrder.get(b.doc_id) ?? -1));
    const extracted = candidates[candidates.length - 1];
    const uploaded = Boolean(extracted) || state.documents.some((doc) => doc.kind === requirement.kind);
    if (!uploaded) return { requirement, uploaded: false, status: "missing", message: "Not added yet" };
    if (!extracted) return { requirement, uploaded: true, status: "uploaded", message: "Added · AI check pending" };

    const values = new Map<string, ExtractedField>(extracted.fields.map((field) => [field.name.toLowerCase(), field]));
    const missing = requirement.requiredFields.filter((aliases) => !aliases.some((name) => {
      const field = values.get(name);
      return field?.value !== null && field?.value !== undefined && String(field.value).trim() !== "";
    }));
    if (missing.length) return { requirement, uploaded: true, status: "review", message: "AI couldn’t find all key details" };
    const keyFields = requirement.requiredFields.map((aliases) => aliases.map((name) => values.get(name)).find(Boolean));
    if (extracted.low_confidence || keyFields.some((field) => !field?.source.snippet.trim() || field.confidence < 0.75)) {
      return { requirement, uploaded: true, status: "review", message: "Check the extracted details" };
    }
    return { requirement, uploaded: true, status: "ready", message: "AI found key details" };
  });
}
