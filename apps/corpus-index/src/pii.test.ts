import { describe, expect, it } from "vitest";
import { assertCleanMetadata, containsRawIdentity, maskPii } from "./pii";

describe("maskPii", () => {
  it("replaces emails, phones and IBANs", () => {
    const masked = maskPii(
      "Write user@example.com or +49 30 12345678. IBAN DE89 3704 0044 0532 0130 00.",
    );
    expect(masked).not.toContain("user@example.com");
    expect(masked).not.toContain("+49");
    expect(masked).not.toContain("DE89");
    expect(masked).toContain("[email]");
    expect(masked).toContain("[phone]");
    expect(masked).toContain("[iban]");
    expect(containsRawIdentity(masked)).toBe(false);
  });

  it("keeps a bare ticket number", () => {
    expect(maskPii("ticket 28312 is open")).toBe("ticket 28312 is open");
  });

  it("drops structured name lines", () => {
    const masked = maskPii("From: Jane Doe <jane@example.com>\nThe invoice is late.");
    expect(masked).not.toContain("Jane");
    expect(masked).not.toContain("jane@example.com");
    expect(masked).toContain("The invoice is late.");
  });
});

describe("assertCleanMetadata", () => {
  it("rejects customer identity keys and raw identity in values", () => {
    expect(() => assertCleanMetadata({ customer: "Jane Doe" })).toThrow("metadata_identity");
    expect(() => assertCleanMetadata({ from: "jane@example.com" })).toThrow("metadata_identity");
    expect(() =>
      assertCleanMetadata({ source: "ticket", content: "mail jane@example.com" }),
    ).toThrow("metadata_identity");
  });

  it("accepts an allowlisted record after masking", () => {
    expect(() =>
      assertCleanMetadata({
        source: "ticket",
        ticket_id: "42",
        state: "closed",
        content: maskPii("See user@example.com"),
        model: "@cf/baai/bge-m3",
      }),
    ).not.toThrow();
  });
});
