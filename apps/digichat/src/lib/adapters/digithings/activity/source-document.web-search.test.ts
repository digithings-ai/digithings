import { describe, expect, it } from "vitest";
import { mapRawSourceToDocument, ragToolDisplayName } from "./source-document";

describe("web_search External cites (#3420)", () => {
  it("maps evidence_tier External onto the activity document", () => {
    const doc = mapRawSourceToDocument({
      doc_id: "https://example.com/a",
      snippet: "Public fact",
      metadata: {
        title: "Example",
        source_url: "https://example.com/a",
        evidence_tier: "External",
        source_kind: "external",
      },
    });
    expect(doc).toMatchObject({
      title: "Example",
      path: "https://example.com/a",
      tier: "External",
    });
  });

  it("infers External from source_kind when tier missing", () => {
    const doc = mapRawSourceToDocument({
      doc_id: "https://example.com/b",
      metadata: { title: "B", source_kind: "external" },
    });
    expect(doc?.tier).toBe("External");
  });

  it("keeps web_search as its own tool display name", () => {
    expect(ragToolDisplayName("web_search")).toBe("web_search");
    expect(ragToolDisplayName("digisearch")).toBe("digisearch");
  });
});
