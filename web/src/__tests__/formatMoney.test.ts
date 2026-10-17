import { describe, expect, it } from "vitest";
import { formatMoney } from "../ui";

describe("formatMoney", () => {
  it("formats positive USD amounts with thousands separators", () => {
    expect(formatMoney(10000000, "USD")).toBe("USD 100,000.00");
    expect(formatMoney(12345, "USD")).toBe("USD 123.45");
  });

  it("formats negative amounts with a leading minus sign", () => {
    expect(formatMoney(-124500, "USD")).toBe("-USD 1,245.00");
    expect(formatMoney(-50n, "USD")).toBe("-USD 0.50");
  });

  it("handles zero decimals for currencies like JPY", () => {
    expect(formatMoney(50000, "JPY")).toBe("JPY 50,000");
    expect(formatMoney(0, "JPY")).toBe("JPY 0");
  });

  it("formats zero amount accurately", () => {
    expect(formatMoney(0, "USD")).toBe("USD 0.00");
    expect(formatMoney(0n, "EUR")).toBe("EUR 0.00");
  });

  it("handles very large BigInt values exceeding 2^53 without precision loss", () => {
    expect(formatMoney("900719925474099100", "USD")).toBe("USD 9,007,199,254,740,991.00");
  });

  it("does not crash on invalid or unknown currency codes", () => {
    expect(formatMoney(10000, "INVALID")).toBe("INVALID 100.00");
    expect(formatMoney(-5000, "XYZ")).toBe("-XYZ 50.00");
  });

  it("handles null and undefined gracefully without throwing", () => {
    expect(formatMoney(undefined, "USD")).toBe("USD 0.00");
    expect(formatMoney(null, "USD")).toBe("USD 0.00");
    expect(formatMoney(undefined, "JPY")).toBe("JPY 0");
  });
});
