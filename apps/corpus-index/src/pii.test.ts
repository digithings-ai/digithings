import { describe, expect, it } from "vitest";
import { assertCleanMetadata, containsRawIdentity, maskPii, namesFrom } from "./pii";

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

describe("name masking (DIG-3269 gate)", () => {
  it("masks quoted mail headers, greetings, closings, known names and companies", () => {
    const names = namesFrom(['"Max Oppenlaender" <max@x.de>', "Jugendhilfe Nord gGmbH"]);
    const raw =
      "Hallo Leon, danke. Viele Grüßen Markus Pflüger t +49 711 1234567 Von: Max Oppenlaender < max@x.de > Gesendet: Dienstag Betreff: Zugang für Frau Hülpert bei Schloss Stutensee gGmbH und Jugendhilfe Nord gGmbH";
    const out = maskPii(raw, names);
    for (const leak of ["Leon", "Markus", "Pflüger", "Oppenlaender", "Hülpert", "Stutensee", "Jugendhilfe", "max@x.de"]) {
      expect(out).not.toContain(leak);
    }
    expect(out).toContain("Hallo [name]");
    expect(out).toContain("Gesendet: Dienstag");
  });
  it("keeps team sign-offs", () => {
    expect(maskPii("Viele Grüße Ihr OCC Team")).toContain("Ihr OCC Team");
  });
});

describe("signature contact details (DIG-3269 gate)", () => {
  it("masks national phones, street, postcode city and website", () => {
    const out = maskPii(
      "fon +49 3491/6181-30 fax +49 3491/6181-18 Musterstraße 22, 65232 Taunusstein Fon 06128/3333 Mobil 0151/12483766 Telefon: 02203-92072-0 Web: www.example-firma.de Industriestr. 8 * DE-65510 Idstein",
    );
    for (const leak of ["3491", "6181", "Musterstraße", "65232", "Taunusstein", "06128", "0151", "02203", "example-firma", "Industriestr", "Idstein"]) {
      expect(out).not.toContain(leak);
    }
  });
});
