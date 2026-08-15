import { describe, expect, it } from "vitest";
import { mapDigisearchRagSources } from "./digisearch";

describe("mapDigisearchRagSources", () => {
  it("maps a zero-hit rag_sources trace to a completed retrieve span with no documents", () => {
    // digigraph now emits this trace on every completed retrieval, hit or
    // miss (see workflow.py's `"rag_sources" in data` gate, bb96fb85e) — the
    // exact wire shape a zero-hit digisearch call produces: an empty
    // `sources` array plus `query`/`hit_count`.
    const span = mapDigisearchRagSources({
      tool: "digisearch",
      query: "jwt",
      sources: [],
      hit_count: 0,
    });

    // Assert the full shape, not just "not null" — a completed retrieve span
    // with no `documents` key is what makes toDigiChatActivity render the
    // honest "no hits" tool_result rather than dropping the span or
    // fabricating a fake one.
    expect(span).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digisearch",
      query: "jwt",
    });
    expect(span).not.toHaveProperty("documents");
  });

  it("omits query when the zero-hit trace carries none", () => {
    const span = mapDigisearchRagSources({ tool: "digisearch", sources: [] });
    expect(span).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digisearch",
    });
  });

  it("still returns null when sources is missing entirely (not a rag_sources trace)", () => {
    expect(mapDigisearchRagSources({ tool: "digisearch" })).toBeNull();
  });

  it("leaves the successful (non-empty) path byte-identical", () => {
    const payload = {
      tool: "digithings_docs",
      query: "SHOWCASE",
      sources: [
        {
          doc_id: "609e63ae-2671-47ad-bf5a-779ff7d8b757",
          snippet: "# ADR 0001: digithings Project Spec",
          metadata: {
            source_url: "repo://digithings/docs/adr/0001-project-spec.md",
          },
        },
      ],
    };
    expect(mapDigisearchRagSources(payload)).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digisearch",
      documents: [
        {
          title: "ADR 0001: digithings Project Spec",
          path: "docs/adr/0001-project-spec.md",
          snippet: "# ADR 0001: digithings Project Spec",
        },
      ],
      query: "SHOWCASE",
    });
  });
});
