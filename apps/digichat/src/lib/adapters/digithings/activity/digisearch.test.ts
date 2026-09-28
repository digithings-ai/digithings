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
      toolInput: { query: "jwt" },
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

  it("prefers MCP arguments over the query-only toolInput", () => {
    const span = mapDigisearchRagSources({
      tool: "digisearch",
      query: "what is digigraph",
      arguments: { query: "what is digigraph", top_k: 6 },
      sources: [
        {
          snippet: "# digigraph",
          metadata: { source_url: "repo://digithings/digigraph/ARCHITECTURE.md" },
        },
      ],
      hit_count: 1,
    });
    expect(span?.toolInput).toEqual({ query: "what is digigraph", top_k: 6 });
    expect(span?.documents?.[0]).toMatchObject({
      path: "digigraph/ARCHITECTURE.md",
      snippet: "# digigraph",
    });
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
      toolInput: { query: "SHOWCASE" },
    });
  });

  it("routes vault search rag_sources onto search_notes with real hit rows", () => {
    const span = mapDigisearchRagSources({
      tool: "digivault_search_notes",
      query: "run digigraph docker command",
      arguments: { query: "run digigraph docker command" },
      sources: [
        {
          doc_id: "clients/digithings/digigraph/ARCHITECTURE.md",
          snippet: "docker compose up digigraph",
          metadata: { title: "digigraph architecture" },
        },
      ],
      hit_count: 1,
    });
    expect(span).toMatchObject({
      operation: "retrieve",
      status: "completed",
      toolName: "digivault_search_notes",
      documents: [
        {
          title: "digigraph architecture",
          path: "clients/digithings/digigraph/ARCHITECTURE.md",
          snippet: "docker compose up digigraph",
        },
      ],
    });
  });

  it("does not render a vault invoke error as hitCount 0", () => {
    const span = mapDigisearchRagSources({
      tool: "digivault_search_notes",
      query: "run digigraph docker command",
      sources: [],
      hit_count: 0,
      status: "failed",
      error: "path_prefix is required when the D1 backend is configured",
    });
    expect(span).toMatchObject({
      operation: "execute_tool",
      status: "failed",
      toolName: "digivault_search_notes",
    });
    expect(span).not.toHaveProperty("hitCount");
    expect(span?.label).toMatch(/path_prefix|failed/i);
  });
});
