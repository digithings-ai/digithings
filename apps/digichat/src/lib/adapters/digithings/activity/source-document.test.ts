import { describe, expect, it } from "vitest";
import {
  mapRawSourceToDocument,
  ragToolDisplayName,
  resolveSourcePath,
  stripRepoPrefix,
} from "./source-document";

describe("stripRepoPrefix", () => {
  it("strips repo://digithings/ prefix", () => {
    expect(stripRepoPrefix("repo://digithings/docs/adr/0001-project-spec.md")).toBe(
      "docs/adr/0001-project-spec.md"
    );
  });
});

describe("resolveSourcePath", () => {
  it("prefers metadata.source_url over opaque doc_id", () => {
    expect(
      resolveSourcePath(
        { doc_id: "609e63ae-2671-47ad-bf5a-779ff7d8b757", source_id: "609e63ae#1" },
        { source_url: "repo://digithings/docs/adr/0001-project-spec.md" }
      )
    ).toBe("docs/adr/0001-project-spec.md");
  });

  it("uses vault_path for digivault hits", () => {
    expect(
      resolveSourcePath(
        { vault_path: "clients/digithings/digithings-docs-projects-digithings-showcase-md" },
        {}
      )
    ).toBe("clients/digithings/digithings-docs-projects-digithings-showcase-md");
  });
});

describe("mapRawSourceToDocument", () => {
  it("derives title from snippet when metadata lacks title", () => {
    const doc = mapRawSourceToDocument({
      doc_id: "8d780bcc-b9f2-4d14-9fa4-6d0a1ea8c901",
      snippet: "# digithings chat — product showcase (client #0)\n\nBody…",
      metadata: {},
    });
    expect(doc).toMatchObject({
      title: "digithings chat — product showcase (client #0)",
      path: "digithings chat — product showcase (client #0)",
    });
  });

  it("maps source_url path and title from metadata", () => {
    const doc = mapRawSourceToDocument({
      source_id: "doc-1",
      snippet: "JWT exchange via digikey",
      metadata: {
        title: "Auth plane",
        source_url: "repo://digithings/digikey/ARCHITECTURE.md",
        evidence_tier: "peer_reviewed",
        publication_year: 2024,
      },
    });
    expect(doc).toMatchObject({
      title: "Auth plane",
      path: "digikey/ARCHITECTURE.md",
      tier: "peer_reviewed",
      year: 2024,
      snippet: "JWT exchange via digikey",
    });
  });

  it("maps get_note rag_sources body onto the activity document", () => {
    const doc = mapRawSourceToDocument({
      doc_id: "clients/digithings/auth__p001",
      snippet: "RS256 tokens…",
      body: "# Auth\n\nFull note from get_note.",
      metadata: { title: "Auth plane" },
    });
    expect(doc).toMatchObject({
      title: "Auth plane",
      path: "clients/digithings/auth__p001",
      snippet: "RS256 tokens…",
      body: "# Auth\n\nFull note from get_note.",
    });
  });
});

describe("ragToolDisplayName", () => {
  it("maps internal tool ids to digisearch/digivault labels", () => {
    expect(ragToolDisplayName("digithings_docs")).toBe("digisearch");
    expect(ragToolDisplayName("digivault_search_notes")).toBe("digivault_search_notes");
    expect(ragToolDisplayName("digivault_get_note")).toBe("digivault_get_note");
    expect(ragToolDisplayName(undefined)).toBe("digisearch");
  });
});
