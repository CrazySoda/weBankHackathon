import { describe, expect, it } from "vitest";
import { RULE_EXPLANATIONS, getRuleExplanation } from "../config/ruleExplanations";

const EXPECTED_BACKEND_RULE_IDS = [
  "lc-invoice-exceeds-lc",
  "lc-currency-mismatch",
  "lc-beneficiary-mismatch",
  "lc-applicant-mismatch",
  "lc-description-inconsistent",
  "lc-quantity-mismatch",
  "ucp600-shipment-after-expiry",
  "ucp600-shipment-after-latest",
  "ucp600-presentation-stale",
  "doc-date-unparseable",
  "sanctions-match",
  "vat-refund-estimate",
  "injection-hidden-text",
  "injection-instruction-phrase",
  "injection-classifier",
];

describe("RULE_EXPLANATIONS", () => {
  it("contains an entry for every known backend rule ID", () => {
    for (const ruleId of EXPECTED_BACKEND_RULE_IDS) {
      const exp = RULE_EXPLANATIONS[ruleId];
      expect(exp).toBeDefined();
      expect(exp.title).toBeTruthy();
      expect(exp.whatThisMeans).toBeTruthy();
      expect(exp.whatToDoNext).toBeTruthy();
      expect(exp.ruleReference).toBeTruthy();
    }
  });

  it("contains accurate UCP 600 Art. 18(b) tooltip and whatToDoNext instructions", () => {
    const art18 = RULE_EXPLANATIONS["lc-invoice-exceeds-lc"];
    expect(art18.jargonTooltip).toContain("only pay up to the LC amount");
    expect(art18.whatToDoNext).toContain("draw only up to the LC amount");
  });

  it("provides a valid structured fallback for unknown rule IDs without crashing", () => {
    const fallback = getRuleExplanation("unknown-custom-rule", "Custom summary", "Custom explanation");
    expect(fallback.title).toBe("Custom summary");
    expect(fallback.whatThisMeans).toBe("Custom explanation");
    expect(fallback.ruleReference).toBe("unknown-custom-rule");
    expect(fallback.whatToDoNext).toBeTruthy();
  });
});
