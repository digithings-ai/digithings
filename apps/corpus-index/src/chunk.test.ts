import { describe, expect, it } from "vitest";
import { chunkWords, htmlToText, prepareBody, stripQuotesAndSignature } from "./chunk";

describe("prepareBody", () => {
  it("strips html, quotes, a signature and an email", () => {
    const raw = [
      "<p>Please reset the portal.</p>",
      "<p>From: Jane Doe &lt;jane@example.com&gt;</p>",
      "<p>On Monday Alex wrote:</p>",
      "<p>&gt; old quoted text</p>",
      "<p>Thanks</p>",
      "-- ",
      "<p>Sent from my phone +49 30 12345678</p>",
    ].join("");
    const text = prepareBody(raw, "text/html");
    expect(text).toContain("Please reset the portal.");
    expect(text).not.toContain("Jane");
    expect(text).not.toContain("jane@example.com");
    expect(text).not.toContain("old quoted text");
    expect(text).not.toContain("+49");
    expect(text).not.toContain("<p>");
  });

  it("chunks about 500 words with overlap", () => {
    const words = Array.from({ length: 1200 }, (_, i) => `w${i}`);
    const chunks = chunkWords(words.join(" "), 500, 50);
    expect(chunks.length).toBeGreaterThan(2);
    expect(chunks[0].split(/\s+/)).toHaveLength(500);
    expect(chunks[1].startsWith("w450")).toBe(true);
  });

  it("drops an empty body", () => {
    expect(htmlToText("<p>   </p>")).toBe("");
    expect(stripQuotesAndSignature("> only quoted")).toBe("");
  });
});
